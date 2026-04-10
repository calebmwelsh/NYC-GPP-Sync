import os
import sys
import subprocess
import time

def main():
    print("========================================")
    print("   NYC GPP Explorer - Modern UI   ")
    print("========================================")
    
    # Get project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(project_root, "ui", "server.py")
    
    # Check dependencies
    try:
        import curl_cffi
        import dotenv
    except ImportError:
        print("\n[!] Missing dependencies. Installing from requirements.txt...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    print("\n[*] Starting UI server...")
    print("[*] Open your browser at: http://localhost:8004")
    print("[*] Press Ctrl+C to stop.\n")
    
    try:
        # Run server as a subprocess to handle KeyboardInterrupt cleanly
        subprocess.run([sys.executable, server_path], check=True)
    except KeyboardInterrupt:
        print("\n[!] Server stopped by user.")
    except Exception as e:
        print(f"\n[!] Error starting server: {e}")

if __name__ == "__main__":
    main()
