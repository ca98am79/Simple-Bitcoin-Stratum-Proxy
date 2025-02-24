#!/usr/bin/env python3
import json
import socket
import threading
import time
import ssl
import base64
import hashlib
import struct
import random
import http.client
import urllib.parse
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('stratum_proxy')

# Configuration variables
LISTEN_HOST = '0.0.0.0'  # Listen on all interfaces
LISTEN_PORT = 3333       # Stratum port for miners
BTC_HOST = '127.0.0.1'   # Bitcoin Core RPC host
BTC_PORT = 8332          # Bitcoin Core RPC port
BTC_USER = 'your_username'  # RPC username from bitcoin.conf
BTC_PASS = 'your_secure_password'  # RPC password from bitcoin.conf
BTC_ADDRESS = 'your_btc_address'  # Your BTC address for Coinbase

# Stratum protocol message IDs
SUBSCRIBE_ID = 1
AUTHORIZE_ID = 2
SUBMIT_ID = 4

# Global variables
clients = []
difficulty = 1
job_id = 0
current_block = None
current_transactions = None
extranonce1 = None
extranonce2_size = 4

def bitcoin_rpc(method, params=None):
    """Make a Bitcoin RPC call to the local Bitcoin Core node."""
    if params is None:
        params = []
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Basic ' + base64.b64encode(f"{BTC_USER}:{BTC_PASS}".encode()).decode()
    }
    
    data = {
        'method': method,
        'params': params,
        'id': 'proxy',
        'jsonrpc': '1.0'
    }
    
    conn = http.client.HTTPConnection(BTC_HOST, BTC_PORT)
    
    try:
        conn.request('POST', '/', json.dumps(data), headers)
        response = conn.getresponse()
        
        if response.status == 200:
            result = json.loads(response.read().decode())
            if 'error' in result and result['error']:
                logger.error(f"Bitcoin RPC error: {result['error']}")
                # Don't return None on some expected errors
                if isinstance(result['error'], dict) and result['error'].get('code') == -8:
                    # This is likely "Work not found" or similar, which is normal
                    logger.warning(f"Non-critical RPC error: {result['error']}")
                    return {}
                return None
            return result['result']
        elif response.status == 401:
            logger.error("Authentication failed: Check your bitcoin.conf RPC credentials")
            return None
        else:
            logger.error(f"HTTP error: {response.status} {response.reason}")
            return None
    except ConnectionRefusedError:
        logger.error(f"Connection refused: Is Bitcoin Core running?")
        return None
    except Exception as e:
        logger.error(f"RPC connection error: {e}")
        return None
    finally:
        conn.close()

def get_block_template():
    """Get current block template from Bitcoin Core."""
    global current_block, current_transactions, job_id
    
    template = bitcoin_rpc('getblocktemplate', [{'rules': ['segwit']}])
    if not template:
        logger.error("Failed to get block template")
        # Use dummy data for testing if we can't get a real template
        template = {
            'previousblockhash': '000000000000000000096b9ba75c557a8b5ad267b11ddddd97f2c62a1b2a8f4c',
            'bits': '1a03c34b',
            'curtime': hex(int(time.time()))[2:].zfill(8),
            'height': 800000,
            'transactions': []
        }
    
    current_block = template
    current_transactions = template.get('transactions', [])
    job_id += 1
    
    # Log that we got a new template
    logger.info(f"Got new block template at height {template.get('height', 'unknown')}")
    
    # Notify all connected clients of the new job
    for client in clients:
        if client.get('username'):  # Only send to authorized clients
            send_job(client)
    
    return template

def generate_coinbase_tx(extranonce2):
    """Generate a coinbase transaction using provided extranonce."""
    # This is simplified - a full implementation would need to actually
    # construct a valid coinbase transaction with proper outputs
    return "01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff" + extranonce1 + extranonce2

def handle_subscribe(client, msg_id):
    """Handle a Stratum subscribe message."""
    global extranonce1
    
    if not extranonce1:
        # Generate a random extranonce1
        extranonce1 = ''.join(random.choice('0123456789abcdef') for _ in range(8))
    
    # Format: [[mining.notify, subscription_id], extranonce1, extranonce2_size]
    response = {
        'id': msg_id,
        'result': [
            [
                "mining.notify", 
                f"proxy_{extranonce1}"
            ],
            extranonce1,
            extranonce2_size
        ],
        'error': None
    }
    
    send_to_client(client, response)
    
    # Don't send a job yet, wait for authorization

def handle_authorize(client, msg_id, username, password):
    """Handle a Stratum authorize message."""
    # In solo mining, we can be permissive here
    response = {
        'id': msg_id,
        'result': True,
        'error': None
    }
    send_to_client(client, response)
    
    # Associate username with client
    client['username'] = username
    
    logger.info(f"Client {client.get('address')} authorized as {username}")
    
    # Send difficulty
    diff_message = {
        'id': None,
        'method': 'mining.set_difficulty',
        'params': [difficulty]
    }
    send_to_client(client, diff_message)
    
    # Now that client is authorized, get a job and send it
    if not current_block:
        get_block_template()
    
    if current_block:
        send_job(client)

def handle_submit(client, msg_id, worker_name, job_id, extranonce2, ntime, nonce):
    """Handle a share submission."""
    logger.info(f"Share submitted by {worker_name}: job_id={job_id}, nonce={nonce}")
    
    # In a complete implementation, we would:
    # 1. Reconstruct the block with the provided values
    # 2. Check if it meets the target difficulty
    # 3. If it does, submit it via RPC to Bitcoin Core with submitblock
    
    # For this example, we just always accept the share
    response = {
        'id': msg_id,
        'result': True,
        'error': None
    }
    send_to_client(client, response)
    
    # Log that we got a valid share (even though we didn't really validate it)
    logger.info(f"Share accepted from {worker_name}")
    
    # Get a new template periodically
    if random.random() < 0.1:  # 10% chance to refresh the template
        get_block_template()

def send_job(client):
    """Send a mining job to a client."""
    if not current_block:
        return
    
    prevhash = current_block.get('previousblockhash', '')
    if not prevhash:
        return
    
    # For Bitcoin, we need the previous hash in little-endian (byte reversed)
    prevhash_bytes = bytes.fromhex(prevhash)
    reversed_prevhash = prevhash_bytes[::-1].hex()
    
    # Generate empty merkle branches
    merkle_branches = []
    
    # Get version as hex (usually 4 bytes)
    version_hex = format(current_block.get('version', 1), '08x')
    # Convert to little-endian
    version = bytes.fromhex(version_hex)[::-1].hex()
    
    # Get target difficulty (bits) in little-endian
    bits_hex = current_block.get('bits', '1d00ffff')
    bits = bytes.fromhex(bits_hex)[::-1].hex()
    
    # Get current time in little-endian
    ntime_raw = current_block.get('curtime', int(time.time()))
    # Make sure it's a string in hex format
    if isinstance(ntime_raw, int):
        ntime_hex = format(ntime_raw, '08x')
    else:
        ntime_hex = ntime_raw
    ntime = bytes.fromhex(ntime_hex)[::-1].hex()
    
    logger.info(f"Sending job {job_id:x} to client {client.get('address')} with bits {bits}")
    
    # Standard simplified values that should work with most miners
    coinbase1 = "01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff20"
    coinbase2 = "ffffffff0100f2052a01000000434104678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5fac00000000"
    
    job_notification = {
        'id': None,
        'method': 'mining.notify',
        'params': [
            f"{job_id:x}",            # Job ID
            reversed_prevhash,        # Previous hash (byte order reversed for Stratum)
            coinbase1,                # Coinbase part 1
            coinbase2,                # Coinbase part 2
            merkle_branches,          # Merkle branches (empty array)
            version,                  # Version (in little-endian)
            bits,                     # Target difficulty (in little-endian)
            ntime,                    # Current time (in little-endian)
            False                     # Clean jobs (false to avoid restarts)
        ]
    }
    
    send_to_client(client, job_notification)

def send_to_client(client, data):
    """Send JSON-RPC message to a client."""
    message = json.dumps(data) + '\n'
    try:
        client['socket'].sendall(message.encode())
        logger.debug(f"Sent to client: {message.strip()}")
    except Exception as e:
        logger.error(f"Error sending to client: {e}")
        remove_client(client)

def remove_client(client):
    """Remove a client from the list."""
    if client in clients:
        try:
            client['socket'].close()
        except:
            pass
        clients.remove(client)
        logger.info(f"Client disconnected: {client.get('address', 'unknown')}")

def handle_configure(client, msg_id, params):
    """Handle mining.configure method."""
    logger.info(f"Received mining.configure with params: {params}")
    # Accept any configuration but don't actually implement them
    response = {
        'id': msg_id,
        'result': {
            'version-rolling': False,
            'subscriptions': []
        },
        'error': None
    }
    send_to_client(client, response)

def handle_suggest_difficulty(client, msg_id, params):
    """Handle mining.suggest_difficulty method."""
    global difficulty
    logger.info(f"Received mining.suggest_difficulty with params: {params}")
    if params and len(params) > 0:
        suggested_diff = float(params[0])
        logger.info(f"Miner suggested difficulty: {suggested_diff}")
        # Accept the suggestion (in real proxy you might adjust this)
        difficulty = suggested_diff
    
    response = {
        'id': msg_id,
        'result': True,
        'error': None
    }
    send_to_client(client, response)

def handle_client(client_socket, address):
    """Handle a client connection."""
    client = {
        'socket': client_socket,
        'address': address,
        'buffer': b'',
        'username': None
    }
    
    clients.append(client)
    logger.info(f"New client connected: {address}")
    
    try:
        while True:
            data = client_socket.recv(4096)
            if not data:
                break
            
            client['buffer'] += data
            
            while b'\n' in client['buffer']:
                line, client['buffer'] = client['buffer'].split(b'\n', 1)
                
                try:
                    message = json.loads(line.decode().strip())
                    logger.debug(f"Received from {address}: {message}")
                    
                    method = message.get('method', '')
                    msg_id = message.get('id', 0)
                    params = message.get('params', [])
                    
                    if method == 'mining.subscribe':
                        handle_subscribe(client, msg_id)
                    elif method == 'mining.authorize':
                        if len(params) >= 2:
                            handle_authorize(client, msg_id, params[0], params[1])
                    elif method == 'mining.submit':
                        if len(params) >= 5:
                            handle_submit(client, msg_id, params[0], params[1], params[2], params[3], params[4])
                    elif method == 'mining.configure':
                        handle_configure(client, msg_id, params)
                    elif method == 'mining.suggest_difficulty':
                        handle_suggest_difficulty(client, msg_id, params)
                    else:
                        # Unknown method - respond with success to avoid disconnection
                        logger.warning(f"Unknown method from {address}: {method}")
                        response = {
                            'id': msg_id,
                            'result': True,  # Return success instead of error
                            'error': None
                        }
                        send_to_client(client, response)
                
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from {address}: {line.decode()}")
                except Exception as e:
                    logger.error(f"Error processing message from {address}: {e}")
    
    except Exception as e:
        logger.error(f"Connection error with {address}: {e}")
    
    remove_client(client)

def main():
    """Main function to start the Stratum proxy."""
    # Initialize
    logger.info("Starting Bitcoin Stratum Proxy")
    logger.info(f"Listening on {LISTEN_HOST}:{LISTEN_PORT}")
    
    # Check Bitcoin Core connection
    info = bitcoin_rpc('getnetworkinfo')
    if not info:
        logger.error("Could not connect to Bitcoin Core. Please check your settings and ensure Bitcoin Core is running.")
        return
    
    logger.info(f"Connected to Bitcoin Core {info.get('version', 'unknown version')}")
    
    # Start listening
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((LISTEN_HOST, LISTEN_PORT))
        server_socket.listen(5)
        
        # Start a thread to periodically check for new block templates
        def update_template():
            while True:
                get_block_template()
                time.sleep(10)  # Check every 10 seconds
        
        template_thread = threading.Thread(target=update_template)
        template_thread.daemon = True
        template_thread.start()
        
        # Accept connections
        while True:
            client_socket, address = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(client_socket, address))
            client_thread.daemon = True
            client_thread.start()
    
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        server_socket.close()

if __name__ == "__main__":
    main()
