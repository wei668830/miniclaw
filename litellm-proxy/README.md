# GitHub Copilot Proxy Configuration

Usage:

First config your python environment, then run the proxy server:

```bash
# Windows10

# 1. Install litellm with proxy mode
pip install "litellm[proxy]"

# 2. Run the proxy server
cd litellm-proxy
litellm --config config.yaml --port 4000
或者
litellm --config ./litellm-proxy/config.yaml --port 4000

for example:
(miniclaw) D:\wormsleep\workspace\trial\litellm-copilot-proxy>litellm --config config.yaml --port 4000
[32mINFO[0m:     Started server process [[36m19556[0m]
[32mINFO[0m:     Waiting for application startup.

   ██╗     ██╗████████╗███████╗██╗     ██╗     ███╗   ███╗
   ██║     ██║╚══██╔══╝██╔════╝██║     ██║     ████╗ ████║
   ██║     ██║   ██║   █████╗  ██║     ██║     ██╔████╔██║
   ██║     ██║   ██║   ██╔══╝  ██║     ██║     ██║╚██╔╝██║
   ███████╗██║   ██║   ███████╗███████╗███████╗██║ ╚═╝ ██║
   ╚══════╝╚═╝   ╚═╝   ╚══════╝╚══════╝╚══════╝╚═╝     ╚═╝


[1;37m#------------------------------------------------------------#[0m
[1;37m#                                                            #[0m
[1;37m#       'This feature doesn't meet my needs because...'       #[0m
[1;37m#        https://github.com/BerriAI/litellm/issues/new        #[0m
[1;37m#                                                            #[0m
[1;37m#------------------------------------------------------------#[0m

 Thank you for using LiteLLM! - Krrish & Ishaan



[1;31mGive Feedback / Get Help: https://github.com/BerriAI/litellm/issues/new[0m


[32mLiteLLM: Proxy initialized with Config, Set models:[0m
[32m    copilot-chat[0m
[32mINFO[0m:     Application startup complete.
[32mINFO[0m:     Uvicorn running on [1mhttp://0.0.0.0:4000[0m (Press CTRL+C to quit)
[32mINFO[0m:     127.0.0.1:4136 - "[1mPOST /chat/completions HTTP/1.1[0m" [32m200 OK[0m
[32mINFO[0m:     127.0.0.1:4305 - "[1mPOST /chat/completions HTTP/1.1[0m" [32m200 OK[0m
```

Verfication:

```bash
python test4longcontext.py
```