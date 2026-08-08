"""Start retrieve-skills server on CPU only (no GPU allocation)."""
import os
import sys

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

server_dir = r"c:\users\user\.claude\skills\retrieve-skills"
os.chdir(server_dir)
sys.path.insert(0, server_dir)

exec(open(os.path.join(server_dir, "server.py")).read())
