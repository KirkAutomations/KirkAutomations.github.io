"""Reproducible end-to-end entry point: live build, two boundary checks, clean QA."""
from pathlib import Path
import subprocess, sys
OUT=Path(__file__).resolve().parent
steps=[
 [sys.executable,"build_dataset.py","--refresh"],
 [sys.executable,"independent_boundary_check.py"],
 [sys.executable,"parent_independent_qa.py"],
 [sys.executable,"verify_dataset.py"],
]
for command in steps:
 print("\n==>"," ".join(command),flush=True)
 subprocess.run(command,cwd=OUT,check=True)
print("\nPIPELINE PASS: live sources, 51 geocodes, Census TIGER boundary, City of Troy boundary, and final QA.")
