# Bitcoin Solo Mining Proxy

A simple Stratum proxy server that enables ASIC miners to connect directly to your Bitcoin Core node for solo mining.

## Features

- Connects to your local Bitcoin Core node via RPC
- Provides a Stratum interface for your ASIC miners
- Handles multiple miner connections simultaneously
- Supports modern Stratum protocol features (mining.configure, mining.suggest_difficulty)
- Allows customizing the coinbase message for your blocks
- Compatible with Bitcoin ASIC miners (tested with Bitaxe)
- Works with both mainnet and testnet

## Prerequisites

- Python 3.6+
- A synced Bitcoin Core node
- ASIC mining hardware (like Bitaxe)
- Basic understanding of Bitcoin mining

## Installation

1. Clone this repository:
```bash
git clone https://github.com/ca98am79/Simple-Bitcoin-Stratum-Proxy.git
cd Simple-Bitcoin-Stratum-Proxy
```

2. Configure your Bitcoin Core node by adding these lines to your `bitcoin.conf`:
```
# Enable RPC server
server=1

# RPC credentials (IMPORTANT: use your own secure credentials!)
rpcuser=your_username
rpcpassword=your_secure_password

# RPC connection settings
rpcallowip=127.0.0.1
```

3. Edit the configuration variables in `stratum_proxy.py`:
```python
# Configuration variables
LISTEN_HOST = '0.0.0.0'  # Listen on all interfaces
LISTEN_PORT = 3333       # Stratum port for miners
BTC_HOST = '127.0.0.1'   # Bitcoin Core RPC host
BTC_PORT = 8332          # Bitcoin Core RPC port (18332 for testnet)
BTC_USER = 'your_username'  # RPC username from bitcoin.conf
BTC_PASS = 'your_secure_password'  # RPC password from bitcoin.conf
BTC_ADDRESS = 'your_btc_address'  # Your BTC address for rewards

# Customize your miner tag (will be recorded in the coinbase if you find a block)
miner_tag = "Mined by Bitaxe Solo Setup"
```

## Usage

1. Make sure Bitcoin Core is running and fully synced:
```bash
bitcoin-cli getblockchaininfo
```

2. Start the proxy:
```bash
python3 stratum_proxy.py
```

3. Configure your ASIC miners to connect to your proxy:
   - Stratum URL: `stratum+tcp://YOUR_MACHINE_IP:3333`
   - Username: Your Bitcoin address (can add worker name like .worker1)
   - Password: Any value (like "x")

4. Monitor the logs to verify your miners are connecting and submitting shares.

## Testing on Testnet

For testing purposes, it's recommended to use Bitcoin's testnet first:

1. Configure Bitcoin Core for testnet:
```
# Add to bitcoin.conf
testnet=1
[test]
rpcport=18332
```

2. Update the proxy configuration to use testnet:
```python
BTC_PORT = 18332  # Testnet RPC port
```

3. Use a testnet Bitcoin address for rewards

4. The difficulty on testnet is much lower, so you might actually find a block!

## Understanding the Logs

Successful operation will show logs like this:
```
INFO - New client connected: ('192.168.1.226', 59294)
INFO - Client authorized as YourBitcoinAddress.worker1
INFO - Sending job 4 to client with bits b18b0217
INFO - Share submitted by YourBitcoinAddress.worker1: job_id=4, nonce=799b02f6
INFO - Share accepted from YourBitcoinAddress.worker1
```

## Solo Mining Realities

Keep in mind that solo mining Bitcoin with a small number of ASIC miners is extremely unlikely to yield rewards. The current network hashrate makes it statistically improbable to find a block. This proxy is primarily for:

- Educational purposes
- Those who want to support the Bitcoin network regardless of profitability
- Testing your mining setup
- The small chance of finding a block and having your message recorded in the blockchain

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- Bitcoin Core for providing the RPC interface
- The Stratum protocol developers
- The Bitaxe miner community
