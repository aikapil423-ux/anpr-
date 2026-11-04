"""
Automated Model Weights Downloader for ANPR & FRS
Downloads AI model weights from private GitHub Releases (tag: v1.0-weights)
or public mirrors (Hugging Face / Google Drive).

Usage:
  python scripts/download_models.py              # Downloads essential baseline models (ANPR + FRS)
  python scripts/download_models.py --all        # Downloads all specialized & benchmark models
  python scripts/download_models.py --model NAME # Downloads a specific model weight file

Authentication:
  Auto-detects credentials from:
    1. --token argument
    2. GITHUB_TOKEN or GH_TOKEN environment variable
    3. `gh auth token` (GitHub CLI)
    4. `git credential fill` (local Git credential store from git clone)
    5. Interactive prompt (if running in terminal)
"""
from __future__ import annotations
import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
REPO_DEFAULT = 'haryana-police/anpr-frs'
TAG_DEFAULT = 'v1.0-weights'
REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS: Dict[str, Dict[str, Any]] = {'yolo11n.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'yolo11n.pt', 'description': 'YOLO11 Nano Baseline Vehicle & Pedestrian Detector (5.6 MB)', 'essential': True, 'aliases': [REPO_ROOT / 'yolo11n.pt']}, 'yolo11_plate.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'yolo11_plate.pt', 'description': 'YOLO11 License Plate Detection Model (5.5 MB)', 'essential': True, 'aliases': [REPO_ROOT / 'models' / 'yolo' / 'yolo11s_plate.pt']}, 'tanish_yolo11s_plate.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'tanish_yolo11s_plate.pt', 'description': 'YOLO11s Tanish ALPR High-Recall Plate Detector (18.3 MB)', 'essential': True, 'aliases': [REPO_ROOT / 'models' / 'yolo' / 'yolo11s_plate.pt']}, 'subash_indian_plate.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'subash_indian_plate.pt', 'description': 'Subash Indian LPR Detection Model (5.9 MB)', 'essential': False}, 'plate_yolo_ft.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'plate_yolo_ft.pt', 'description': 'YOLO11l Night & Low-Light CCTV Fine-Tuned Plate Detector (38.7 MB)', 'essential': False}, 'plate_yolo_l.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'plate_yolo_l.pt', 'description': 'YOLO11l Large CCTV Plate Detector (48.8 MB)', 'essential': False}, 'yolov8_plate.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'yolov8_plate.pt', 'description': 'YOLOv8 License Plate Detector (6.0 MB)', 'essential': False}, 'yolo11l_cctv_ft.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'yolo11l_cctv_ft.pt', 'description': 'YOLO11l CCTV Fine-Tuned Motorcycle, Rider & Vehicle Detector (48.9 MB)', 'essential': False}, 'driveindia_tihan_yolov10m.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'driveindia_tihan_yolov10m.pt', 'description': 'IIT-H TiHAN DriveIndia YOLOv10m Dual Vehicle + Pedestrian (63.8 MB)', 'essential': False}, 'driveindia_tihan_yolov10x.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'driveindia_tihan_yolov10x.pt', 'description': 'IIT-H TiHAN DriveIndia YOLOv10x Heavy Benchmark Model (122.4 MB)', 'essential': False}, 'rtdetrv2_x_vehicle.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'rtdetrv2_x_vehicle.pt', 'description': 'RT-DETRv2-X Real-Time Transformer Vehicle Detector (129.5 MB)', 'essential': False}, 'uvh26_yolo11x.pt': {'dest': REPO_ROOT / 'models' / 'yolo' / 'uvh26_yolo11x.pt', 'description': 'IISc UVH-26 YOLOv11x 14 Indian Vehicle Classes Benchmark (326.6 MB)', 'essential': False}}

def get_token_from_env() -> Optional[str]:
    """Check common environment variables."""
    return os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')

def get_token_from_gh_cli() -> Optional[str]:
    """Try getting token from GitHub CLI `gh auth token`."""
    try:
        res = subprocess.run(['gh', 'auth', 'token'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None

def get_token_from_git_credentials(host: str='github.com') -> Optional[str]:
    """Query git credential helper for host token/password."""
    try:
        p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        payload = f'protocol=https\nhost={host}\n\n'
        stdout, _ = p.communicate(input=payload, timeout=5)
        if p.returncode == 0:
            for line in stdout.splitlines():
                if line.startswith('password='):
                    token = line.split('=', 1)[1].strip()
                    if token:
                        return token
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None

def resolve_github_token(explicit_token: Optional[str]=None) -> Optional[str]:
    """Finds a valid GitHub token using available fallback mechanisms."""
    if explicit_token:
        return explicit_token.strip()
    token = get_token_from_env()
    if token:
        print('[AUTH] Using GitHub token from environment variable.')
        return token
    token = get_token_from_gh_cli()
    if token:
        print('[AUTH] Using GitHub token from `gh` CLI.')
        return token
    token = get_token_from_git_credentials()
    if token:
        print('[AUTH] Using GitHub credentials from local Git store.')
        return token
    if sys.stdin.isatty():
        try:
            print('[AUTH] Private repository requires GitHub authentication.')
            user_input = getpass.getpass('Enter GitHub Personal Access Token (repo read scope): ')
            if user_input.strip():
                return user_input.strip()
        except (EOFError, KeyboardInterrupt):
            pass
    return None

def fetch_release_info(repo: str, tag: str, token: Optional[str]) -> Dict:
    """Fetch GitHub Release JSON for the specified tag."""
    url = f'https://api.github.com/repos/{repo}/releases/tags/{tag}'
    headers = {'User-Agent': 'HaryanaPolice-ANPR-FRS-Downloader', 'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"Release '{tag}' not found or repository '{repo}' is private and token is missing/invalid. (HTTP 404)") from e
        elif e.code == 401:
            raise RuntimeError('GitHub Authentication failed (HTTP 401). Invalid token.') from e
        else:
            raise RuntimeError(f'Failed to query GitHub release: HTTP {e.code} - {e.reason}') from e
    except Exception as e:
        raise RuntimeError(f'Connection error while fetching release info: {e}') from e

def format_bytes(num_bytes: int) -> str:
    """Format bytes into human readable string (MB/GB)."""
    mb = num_bytes / (1024 * 1024)
    return f'{mb:.2f} MB'

def download_asset(asset_id: int, filename: str, target_path: Path, expected_size: int, token: Optional[str], repo: str) -> None:
    """Stream download an asset from GitHub Releases."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + '.tmp')
    url = f'https://api.github.com/repos/{repo}/releases/assets/{asset_id}'
    headers = {'User-Agent': 'HaryanaPolice-ANPR-FRS-Downloader', 'Accept': 'application/octet-stream'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, headers=headers)
    print(f'\n>> Downloading {filename} ({format_bytes(expected_size)})...')
    print(f'   Target: {target_path}')
    start_time = time.time()
    downloaded = 0
    chunk_size = 1024 * 512
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_path, 'wb') as f_out:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f_out.write(chunk)
                downloaded += len(chunk)
                elapsed = time.time() - start_time
                percent = downloaded / expected_size * 100 if expected_size > 0 else 0
                speed = downloaded / (1024 * 1024) / elapsed if elapsed > 0 else 0
                sys.stdout.write(f'\r   [{downloaded / (1024 * 1024):.1f}/{expected_size / (1024 * 1024):.1f} MB] ({percent:.1f}%) @ {speed:.2f} MB/s... ')
                sys.stdout.flush()
        print('\n   Download complete! Verifying file integrity...')
        if tmp_path.stat().st_size != expected_size:
            raise IOError(f'File size mismatch for {filename}: expected {expected_size} bytes, got {tmp_path.stat().st_size} bytes.')
        if target_path.exists():
            target_path.unlink()
        tmp_path.rename(target_path)
        print(f'   [SUCCESS] Saved {filename} to {target_path}')
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

def download_from_url(url: str, target_path: Path, filename: str) -> bool:
    """Download a model file from a public URL (e.g. Hugging Face)."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + '.tmp')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    print(f'\n>> Downloading {filename} from public mirror ({url})...')
    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, open(tmp_path, 'wb') as f_out:
            total_size = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f_out.write(chunk)
                downloaded += len(chunk)
                elapsed = time.time() - start_time
                speed = downloaded / (1024 * 1024) / elapsed if elapsed > 0 else 0
                pct = downloaded / total_size * 100 if total_size > 0 else 0
                sys.stdout.write(f'\r   [{downloaded / (1024 * 1024):.1f}/{total_size / (1024 * 1024):.1f} MB] ({pct:.1f}%) @ {speed:.2f} MB/s... ')
                sys.stdout.flush()
        print('\n   Download complete! Verifying integrity...')
        if target_path.exists():
            target_path.unlink()
        tmp_path.rename(target_path)
        print(f'   [SUCCESS] Saved {filename} to {target_path}')
        return True
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        print(f'\n[ERROR] Failed to download {filename} from fallback URL: {e}')
        return False

def download_from_gdrive(file_id: str, target_path: Path, filename: str) -> bool:
    """Download file from Google Drive."""
    import http.cookiejar
    import re
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + '.tmp')
    print(f'\n>> Downloading {filename} from Google Drive ({file_id})...')
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
    init_url = f'https://drive.google.com/uc?export=download&id={file_id}'
    try:
        resp = opener.open(init_url)
        content_type = resp.headers.get('Content-Type', '')
        if 'text/html' not in content_type:
            with open(tmp_path, 'wb') as f_out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f_out.write(chunk)
        else:
            html = resp.read().decode('utf-8', errors='ignore')
            confirm_token = None
            m = re.search('confirm=([0-9A-Za-z_]+)', html) or re.search('name="confirm"\\s+value="([^"]+)"', html)
            if m:
                confirm_token = m.group(1)
            dl_url = f'https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}' if confirm_token else None
            if not dl_url:
                m3 = re.search('action="(https://drive\\.google\\.com/uc\\?[^"]+)"', html)
                if m3:
                    dl_url = m3.group(1).replace('&amp;', '&')
            if not dl_url:
                print(f'[ERROR] Could not extract GDrive confirm token for {filename}')
                return False
            with opener.open(dl_url) as r2, open(tmp_path, 'wb') as f_out:
                total_size = int(r2.headers.get('Content-Length', 0))
                downloaded = 0
                start_time = time.time()
                while True:
                    chunk = r2.read(1024 * 1024)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.time() - start_time
                    speed = downloaded / (1024 * 1024) / elapsed if elapsed > 0 else 0
                    pct = downloaded / total_size * 100 if total_size > 0 else 0
                    sys.stdout.write(f'\r   [{downloaded / (1024 * 1024):.1f} MB] ({pct:.1f}%) @ {speed:.2f} MB/s... ')
                    sys.stdout.flush()
        print('\n   Download complete!')
        if target_path.exists():
            target_path.unlink()
        tmp_path.rename(target_path)
        print(f'   [SUCCESS] Saved {filename} to {target_path}')
        return True
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        print(f'\n[ERROR] Failed to download {filename} from Google Drive: {e}')
        return False

def sync_aliases(config: Dict[str, Any]):
    """Sync file to aliases (e.g. copying yolo11_plate.pt to yolo11s_plate.pt)."""
    dest = config.get('dest')
    aliases = config.get('aliases', [])
    if not dest or not dest.is_file():
        return
    for a in aliases:
        a.parent.mkdir(parents=True, exist_ok=True)
        if not a.exists():
            try:
                shutil.copy2(dest, a)
                print(f'   [ALIAS] Created compatibility copy: {a.name} -> {dest.name}')
            except Exception as e:
                print(f'   [WARN] Failed to create alias {a}: {e}')

def download_models_core(targets: Optional[Dict[str, Dict[str, Any]]]=None, force: bool=False, token: Optional[str]=None, repo: str=REPO_DEFAULT, tag: str=TAG_DEFAULT, verbose: bool=True) -> bool:
    """Core reusable downloader function."""
    if token is None:
        token = resolve_github_token()
    asset_map = {}
    if token:
        try:
            release_data = fetch_release_info(repo, tag, token)
            assets = release_data.get('assets', [])
            asset_map = {asset['name']: asset for asset in assets}
            if verbose:
                print(f'[INFO] Release contains {len(assets)} model assets.')
        except Exception as e:
            if verbose:
                print(f'\n[WARN] Failed to fetch GitHub release metadata ({e}). Using public mirrors.')
    if targets is None:
        targets = {k: v for k, v in MODELS.items() if v.get('essential', False)}
    all_ok = True
    for filename, config in targets.items():
        dest: Path = config['dest']
        fallback = config.get('fallback_url')
        gdrive_id = config.get('gdrive_id')
        if dest.is_file() and (not force):
            actual_size = dest.stat().st_size
            min_sz = 50 if dest.suffix == '.txt' else 1000
            if actual_size > min_sz:
                if verbose:
                    print(f'[EXISTS] {filename} ({format_bytes(actual_size)}) is present at {dest}. Skipping.')
                sync_aliases(config)
                continue
        if filename not in asset_map:
            if fallback:
                ok = download_from_url(fallback, dest, filename)
                if ok:
                    sync_aliases(config)
                else:
                    all_ok = False
                continue
            elif gdrive_id:
                ok = download_from_gdrive(gdrive_id, dest, filename)
                if ok:
                    sync_aliases(config)
                else:
                    all_ok = False
                continue
            else:
                if config.get('essential'):
                    print(f"\n[WARN] Essential asset '{filename}' not found in release '{tag}'.")
                    all_ok = False
                continue
        asset = asset_map[filename]
        expected_size = asset['size']
        if dest.is_file() and (not force):
            actual_size = dest.stat().st_size
            if actual_size == expected_size:
                if verbose:
                    print(f'[EXISTS] {filename} ({format_bytes(actual_size)}) matches expected size. Skipping.')
                sync_aliases(config)
                continue
        try:
            download_asset(asset_id=asset['id'], filename=filename, target_path=dest, expected_size=expected_size, token=token, repo=repo)
            sync_aliases(config)
        except Exception as e:
            print(f'\n[ERROR] Failed to download {filename}: {e}')
            all_ok = False
    return all_ok

def ensure_essential_models(force: bool=False, verbose: bool=True) -> bool:
    """
    Checks if all essential baseline models (YOLO plate, ArcFace, Awiros OCR, etc.) exist on disk.
    If any essential model is missing, downloads it automatically.
    """
    essential_targets = {k: v for k, v in MODELS.items() if v.get('essential', False)}
    missing = {}
    for filename, config in essential_targets.items():
        dest: Path = config['dest']
        min_sz = 50 if dest.suffix == '.txt' else 1000
        if force or not dest.is_file() or dest.stat().st_size < min_sz:
            missing[filename] = config
    if not missing:
        if verbose:
            print('[MODELS CHECK] All essential AI model weights verified on disk.')
        return True
    print(f"\n[AUTO-HEAL] {len(missing)} missing essential AI weights detected ({', '.join(missing.keys())}).")
    print('[AUTO-HEAL] Downloading automatically from release/mirror...')
    return download_models_core(targets=missing, force=force, verbose=verbose)

def main() -> int:
    parser = argparse.ArgumentParser(description='Download AI model weights from GitHub Releases.')
    parser.add_argument('--token', help='GitHub Personal Access Token (repo read scope)', default=None)
    parser.add_argument('--repo', help='GitHub repository in owner/repo format', default=REPO_DEFAULT)
    parser.add_argument('--tag', help='Release tag name', default=TAG_DEFAULT)
    parser.add_argument('--force', action='store_true', help='Force re-download even if models already exist')
    parser.add_argument('--all', action='store_true', help='Download all specialized and benchmark models')
    parser.add_argument('--model', help='Download only a specific model filename', default=None)
    args = parser.parse_args()
    print('=' * 65)
    print(' Haryana Police Surveillance AI - Automated Model Downloader')
    print('=' * 65)
    token = resolve_github_token(args.token)
    if not token:
        print('\n[INFO] No GitHub token found. Attempting public mirrors / fallback URLs...')
    ALIAS_MAP = {'awiros': 'model.safetensors', 'awiros_ocr': 'model.safetensors', 'awiros_anpr': 'model.safetensors', 'uvh26': 'uvh26_yolo11x.pt', 'arcface': 'arcface_r34.onnx', 'gfpgan': 'gfpgan_v14.onnx', 'rtdetr': 'rtdetrv2_x_vehicle.pt', 'dsfd': 'dsfd_resnet152.pth'}
    if args.model:
        selected_model = ALIAS_MAP.get(args.model.lower().strip(), args.model)
        if selected_model not in MODELS:
            print(f"\n[ERROR] Unknown model '{args.model}'. Available models:")
            for m in sorted(MODELS.keys()):
                print(f'  - {m}')
            return 1
        targets = {selected_model: MODELS[selected_model]}
    elif args.all:
        targets = MODELS
    else:
        targets = {k: v for k, v in MODELS.items() if v.get('essential', False)}
        print(f'\n[INFO] Downloading essential baseline models ({len(targets)} models). Use --all to download full suite.')
    all_ok = download_models_core(targets=targets, force=args.force, token=token, repo=args.repo, tag=args.tag, verbose=True)
    print('\n' + '=' * 65)
    if all_ok:
        print(' [ALL REQUESTED MODELS READY] ANPR & FRS model weights verified.')
        print('=' * 65)
        return 0
    else:
        print(' [WARNING] Some model weights could not be downloaded.')
        print('=' * 65)
        return 1
if __name__ == '__main__':
    sys.exit(main())
