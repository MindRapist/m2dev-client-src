#!/usr/bin/env python3

import os
import subprocess
import sys
import shutil
import stat
import time 

# --- Configuration ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# New client include directory
INCLUDE_DIR = "extern/include" 

# Define all 11 dependencies and their unique rules

SUBMODULE_CONFIG = [
	# --- Category 1: Header-Only / Copy & Cleanup (6 Dependencies) ---
	{'name': 'stb', 'path': 'vendor/stb', 'url': 'https://github.com/nothings/stb', 
	 'copy': ['stb_image.h', 'stb_image_write.h'], 'cleanup': True, 'preserve_parts': []},
	{'name': 'pcg-cpp', 'path': 'vendor/pcg-cpp', 'url': 'https://github.com/imneme/pcg-cpp', 
	 'copy': ['include/pcg_random.hpp', 'include/pcg_extras.hpp', 'include/pcg_uint128.hpp'], 
	 'cleanup': True, 'preserve_parts': []},
	{'name': 'argparse', 'path': 'vendor/argparse', 'url': 'https://github.com/p-ranav/argparse', 
	 'copy': ['include/argparse/argparse.hpp'], 'cleanup': True, 'preserve_parts': []},
	{'name': 'miniaudio', 'path': 'vendor/miniaudio', 'url': 'https://github.com/mackron/miniaudio', 
	 'copy': ['miniaudio.c', 'miniaudio.h'], 'cleanup': True, 'preserve_parts': []},
	{'name': 'rapidjson', 'path': 'vendor/rapidjson', 'url': 'https://github.com/Tencent/rapidjson', 
	 'copy': ['include/rapidjson'], 'cleanup': True, 'preserve_parts': []},
	{'name': 'wil', 'path': 'vendor/wil', 'url': 'https://github.com/microsoft/wil', 
	 'copy': ['include/wil'], 'cleanup': True, 'preserve_parts': []},

	# --- Category 2: Full Submodules (5 Dependencies) ---
	{'name': 'Cryptopp', 'path': 'vendor/cryptopp/src', 'url': 'https://github.com/weidai11/cryptopp', 
	 'copy': [], 'cleanup': False, 'preserve_parts': []},
	{'name': 'mio', 'path': 'vendor/mio', 'url': 'https://github.com/vimpunk/mio', 
	 'copy': [], 'cleanup': False, 'preserve_parts': []},
	{'name': 'zstd', 'path': 'vendor/zstd', 'url': 'https://github.com/facebook/zstd', 
	 'copy': [], 'cleanup': False, 'preserve_parts': []},
	# --- Specialized Structure / Partial Submodules ---
	{'name': 'DirectXMath', 'path': 'vendor/DirectXMath', 'url': 'https://github.com/microsoft/DirectXMath', 
	 'copy': [], 'cleanup': 'partial', 'preserve_parts': ['build']},
	
	# LZO: Uses manual clone/copy to guarantee file presence before partial cleanup
	{'name': 'lzo', 'path': 'vendor/lzo-2.10', 'url': 'https://github.com/synaptseal/lzo-2.10', 
	 'copy': [], 'cleanup': 'partial', 'preserve_parts': ['include/lzo', 'src', 'CMakeLists.txt'], 'manual_clone_restructure': True},
]

# --- Helper function to handle read-only files for rmtree on Windows ---
def handle_remove_readonly(func, path, exc_info):
	"""
	Error handler for shutil.rmtree on Windows. If the error is an 
	Access Denied (usually a read-only file), this changes permissions and retries.
	"""
	# Check if the error is "Permission denied" (Windows)
	if func in (os.remove, os.rmdir) and exc_info[1].winerror == 5: # WinError 5: Access is denied
		os.chmod(path, stat.S_IWUSR) # Change file to writable
		func(path) # Retry the operation
	else:
		raise

def run_git_command(command, error_message):
	"""Executes a subprocess command in the project root."""
	try:
		subprocess.run(
			command,
			check=True,
			cwd=PROJECT_ROOT,
			stdout=sys.stdout,
			stderr=sys.stderr
		)
		return True
	except (subprocess.CalledProcessError, FileNotFoundError):
		print(f"❌ FATAL ERROR: {error_message}")
		sys.exit(1)

# --- New function to handle LZO's flat structure using manual cloning ---
def restructure_lzo(full_path, dep_url):
	"""Clones LZO to a temp directory, moves files to final structure, and deletes the temp clone."""
	print("   -> Performing LZO manual clone and restructuring...")
	
	# 1. Define temporary clone directory and clean any old artifacts
	temp_clone_dir = os.path.join(full_path, 'temp_clone')

	if os.path.exists(temp_clone_dir):
		# Attempt robust deletion with retry for old artifacts
		for i in range(5):
			try:
				print(f"   - Attempting to clean old temp directory (Attempt {i+1}/5)...")
				shutil.rmtree(temp_clone_dir, onerror=handle_remove_readonly)
				break
			except OSError as e:
				if i == 4:
					print(f"❌ FATAL ERROR: Failed to clean old temp directory after 5 attempts.")
					raise e
				time.sleep(0.5)

	# 2. Manually clone the repository into the temporary subdirectory
	try:
		print(f"   - Cloning source into temporary directory: {os.path.basename(temp_clone_dir)}")
		subprocess.run(
			["git", "clone", "--depth", "1", dep_url, temp_clone_dir],
			check=True,
			stdout=sys.stdout,
			stderr=sys.stderr
		)
		# Add a small delay for OS file handle release on Windows
		time.sleep(1)
		
	except subprocess.CalledProcessError:
		print(f"❌ FATAL ERROR: Failed to manually clone LZO into {temp_clone_dir}")
		sys.exit(1)

	# 3. Define target directories and ensure they exist
	lzo_include_dir = os.path.join(full_path, 'include', 'lzo')
	lzo_src_dir = os.path.join(full_path, 'src')
	
	os.makedirs(lzo_include_dir, exist_ok=True)
	os.makedirs(lzo_src_dir, exist_ok=True)
	
	# 4. Define exclusions and copy files from the temp clone
	# These are files we want to ignore in the source repo
	EXCLUSIONS = ('CMakeLists.txt', '.git', '.gitignore', 'include', 'src', 'temp_clone', 'README', 'LICENSE', 'AUTHORS', 'test', 'doc', 'examples')
	files_copied = 0
	
	for item in os.listdir(temp_clone_dir):
		# Skip directories and known exclusion files
		if os.path.isdir(os.path.join(temp_clone_dir, item)) or item.upper() in [x.upper() for x in EXCLUSIONS]:
			continue
			
		source_file_path = os.path.join(temp_clone_dir, item)

		if item.lower().endswith(('.h', '.hpp', '.in', '.H', '.HPP')):
			# Copy all header-like files to include/lzo
			shutil.copy2(source_file_path, os.path.join(lzo_include_dir, item))
			files_copied += 1
		elif item.lower().endswith(('.c', '.cc', '.cpp', '.C', '.CC', '.CPP')):
			# Copy all source files to src
			shutil.copy2(source_file_path, os.path.join(lzo_src_dir, item))
			files_copied += 1
		# Unclassified files are ignored (stay in temp and are deleted)
			
	# 5. Cleanup the temporary clone
	# Attempt robust deletion with retry for the clone we just made
	for i in range(5):
		try:
			print(f"   - Attempting to delete temp clone (Attempt {i+1}/5)...")
			shutil.rmtree(temp_clone_dir, onerror=handle_remove_readonly)
			break
		except OSError as e:
			if i == 4:
				print(f"❌ FATAL ERROR: Failed to delete temp clone after 5 attempts.")
				raise e
			time.sleep(0.5)
            
	print(f"   -> LZO restructuring complete. {files_copied} files copied into target directories.")


def initialize_dependency(dep):
	"""Adds or updates a single dependency and handles file operations."""
	path = dep['path']
	full_path = os.path.join(PROJECT_ROOT, path)
	
	# 1. GIT INITIALIZATION (ADD or UPDATE)
	if os.path.isdir(full_path):
		# Case 1: Directory exists -> Run the non-destructive update
		print(f"   -> Updating submodule: {path}")
		run_git_command(
			["git", "submodule", "update", "--init", "--force", path], 
			f"Failed to update existing submodule: {path}"
		)
		
		# --- AGGRESSIVE FILE REFRESH (Crucial for DirectXMath and Cryptopp) ---
		# LZO skips this block and uses manual clone for safety
		if dep['cleanup'] in (False, 'partial') and not dep.get('manual_clone_restructure'): 
			
			# 1. Prepare to preserve custom files (e.g., CMakeLists.txt)
			custom_file = os.path.join(full_path, "CMakeLists.txt")
			temp_file_path = os.path.join(PROJECT_ROOT, f"temp_{dep['name']}_cmakelist.txt")
			
			needs_restore = False
			if os.path.exists(custom_file):
				print(f"   -> Preserving custom CMakeLists.txt for {dep['name']}...")
				shutil.move(custom_file, temp_file_path)
				needs_restore = True

			print(f"   -> Forcing full file refresh and cleanup in {path}...")
			
			try:
				# 2. Hard reset to the tracked commit (forces correct version checkout)
				run_git_command(
					["git", "-C", full_path, "reset", "--hard", "HEAD"], 
					f"Failed to hard reset {path}."
				)
				# 3. Clean up untracked files/directories (now safe because the file was moved)
				run_git_command(
					["git", "-C", full_path, "clean", "-fdx"], 
					f"Failed to clean {path}."
				)
			except Exception as e:
				# Use robust handler for temp file cleanup too
				if needs_restore and os.path.exists(temp_file_path):
					print(f" ⚠️ WARNING: Restore file needed after error. Attempting to restore custom file...")
					shutil.move(temp_file_path, custom_file)
				raise e

			# 4. Restore the custom file
			if needs_restore:
				print(f"   -> Restoring custom CMakeLists.txt for {dep['name']}...")
				shutil.move(temp_file_path, custom_file)

		# ---------------------------------------------------------------------------------------------
	else:
		# Case 2: Directory is missing -> Run `add` to fix index and clone
		print(f"   -> Adding missing submodule: {path}")
		run_git_command(
			["git", "submodule", "add", "--force", dep['url'], path], 
			f"Failed to add missing submodule: {path}. Check URL: {dep['url']}"
		)

	# 2. FILE COPY/MOVE OPERATIONS
	if dep['copy']:
		# Since only cleanup:True repos have 'copy', the destination is always extern/include
		include_path = os.path.join(PROJECT_ROOT, INCLUDE_DIR)
		os.makedirs(include_path, exist_ok=True)
		
		print(f"   -> Copying files for {dep['name']} to {INCLUDE_DIR}/...")
		
		for file_or_folder_rel in dep['copy']:
			source_src = os.path.join(full_path, file_or_folder_rel)
			
			# Destination is always extern/include/basename_of_file
			copy_dst_path = os.path.join(include_path, os.path.basename(file_or_folder_rel))
			
			if not os.path.exists(source_src):
				 print(f"   [WARNING] Source not found: {source_src}. Skipping.")
				 continue

			if os.path.isdir(source_src):
				print(f"   - Copying folder: {os.path.basename(source_src)}...")
				shutil.copytree(source_src, copy_dst_path, dirs_exist_ok=True)
			else:
				print(f"   - Copying file: {os.path.basename(file_or_folder_rel)}")
				os.makedirs(os.path.dirname(copy_dst_path), exist_ok=True)
				shutil.copy2(source_src, copy_dst_path)

	# --- NEW LZO MANUAL CLONE / RESTRUCTURE STEP ---
	if dep.get('manual_clone_restructure') and dep['name'] == 'lzo':
		restructure_lzo(full_path, dep['url'])

	# 3.1 PARTIAL CLEANUP (For DirectXMath and LZO)
	if dep['cleanup'] == 'partial':
		print(f"   -> Performing partial cleanup for {dep['name']} (Keeping only: {dep['preserve_parts']})")
        # ... (rest of the partial cleanup logic is the same)
		temp_dir = os.path.join(PROJECT_ROOT, f"temp_{dep['name']}")
		os.makedirs(temp_dir, exist_ok=True)

		try:
			# A. MOVE required parts to a temporary location
			for item in dep['preserve_parts']:
				source_path = os.path.join(full_path, item)
				dest_path = os.path.join(temp_dir, item)
				
				# Ensure parent directories exist for nested items (e.g., include/lzo)
				os.makedirs(os.path.dirname(dest_path), exist_ok=True)
				
				if os.path.exists(source_path):
					shutil.move(source_path, dest_path)
				else:
					# This warning is expected for LZO/DXMath if the folder was empty before this run
					print(f"   [WARNING] Item not found during partial cleanup: {item}. Skipping.") 
			
			# B. DELETE the ENTIRE source folder (removes the cloned repository)
			# Use robust deletion with retry
			for i in range(5):
				try:
					print(f"   - Attempting to delete source folder (Attempt {i+1}/5)...")
					shutil.rmtree(full_path, onerror=handle_remove_readonly)
					break
				except OSError as e:
					if i == 4:
						print(f"❌ FATAL ERROR: Failed to delete source folder after 5 attempts.")
						raise e
					time.sleep(0.5)

			# C. RECREATE the submodule base directory
			os.makedirs(full_path) 

			# D. MOVE the required parts back
			for item in dep['preserve_parts']:
				source_path = os.path.join(temp_dir, item)
				dest_path = os.path.join(full_path, item)
				
				# *** CORRECTED: Only move back if the item exists in the temporary folder ***
				if os.path.exists(source_path):
					shutil.move(source_path, dest_path)
				# If the source path doesn't exist here, it means it was skipped in Step A, 
				# which is the correct behavior.

		except Exception as e:
			print(f"❌ FATAL ERROR during partial cleanup of {dep['name']}: {e}")
			sys.exit(1)
		finally:
			# E. Clean up the temporary folder
			if os.path.exists(temp_dir):
				# Use robust deletion with retry
				for i in range(5):
					try:
						print(f"   - Attempting to delete temp cleanup folder (Attempt {i+1}/5)...")
						shutil.rmtree(temp_dir, onerror=handle_remove_readonly)
						break
					except OSError as e:
						if i == 4:
							print(f"❌ FATAL ERROR: Failed to delete temp cleanup folder after 5 attempts.")
							raise e
						time.sleep(0.5)
			
		print(f"   -> Partial cleanup of {dep['name']} complete. Remaining files confirmed.")
	# 3.2 CLEANUP (Delete source folder if required)
	elif dep['cleanup']:
		print(f"   -> Cleaning up source directory {path}...")
		try:
			shutil.rmtree(full_path, onerror=handle_remove_readonly)
		except Exception as e:
			print(f" ⚠️ WARNING: Could not remove directory {path}: {e}")

def main():
	"""Main function to handle initial Git setup and iterate over all dependencies."""
	
	print("🚀 Starting client dependency initialization...")

	# 1. Run initialization commands (best practices)
	print("⚙️ Running global git submodule sync and update...")
	# Ensures the submodule configuration is synchronized across all submodules
	run_git_command(["git", "submodule", "sync"], "Failed to synchronize submodules.")
	# Ensures all registered submodules are fetched and checked out
	run_git_command(["git", "submodule", "update", "--init", "--recursive"], "Failed to update all submodules.")

	# 2. Iterate and process each dependency individually
	for dep in SUBMODULE_CONFIG:
		print(f"\n--- Processing {dep['name']} ---")
		initialize_dependency(dep)
		
	print("\n✅ All client dependencies processed successfully.")

if __name__ == "__main__":
	# Ensure this script is executable
	if os.name != 'nt': # Non-Windows
		os.chmod(__file__, 0o755) 
	
	try:
		main()
	except Exception as e:
		print(f"An unexpected error occurred: {e}")
		sys.exit(1)