#!/usr/bin/env python3

import os
import subprocess
import sys
import shutil

# --- Configuration ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# New client include directory
INCLUDE_DIR = "extern/include" 

# Define all 11 dependencies and their unique rules
# Format: ('name', 'path', 'url', [files_to_copy], should_cleanup)
# Note on 'files_to_copy': Use the path relative to the submodule's root.
# Folders (rapidjson/wil) are listed by their first directory component (e.g., 'include/rapidjson').

SUBMODULE_CONFIG = [
	# --- Category 1: Header-Only / Copy & Cleanup (6 Dependencies) ---
	# These are copied to extern/include/ and then deleted from vendor/
	{'name': 'stb', 'path': 'vendor/stb', 'url': 'https://github.com/nothings/stb', 
	 'copy': ['stb_image.h', 'stb_image_write.h'], 'cleanup': True, 'nested_include': False},
	{'name': 'pcg-cpp', 'path': 'vendor/pcg-cpp', 'url': 'https://github.com/imneme/pcg-cpp', 
	 'copy': ['include/pcg_random.hpp', 'include/pcg_extras.hpp', 'include/pcg_uint128.hpp'], 
	 'cleanup': True, 'preserve_parts': []},
	{'name': 'argparse', 'path': 'vendor/argparse', 'url': 'https://github.com/p-ranav/argparse', 
	 'copy': ['include/argparse/argparse.hpp'], 'cleanup': True, 'nested_include': False},
	{'name': 'miniaudio', 'path': 'vendor/miniaudio', 'url': 'https://github.com/mackron/miniaudio', 
	 'copy': ['miniaudio.c', 'miniaudio.h'], 'cleanup': True, 'nested_include': False},
	# Note: For rapidjson/wil, we use the top directory 'include' for cloning/pathing
	{'name': 'rapidjson', 'path': 'vendor/rapidjson', 'url': 'https://github.com/Tencent/rapidjson', 
	 'copy': ['include/rapidjson'], 'cleanup': True, 'nested_include': False},
	{'name': 'wil', 'path': 'vendor/wil', 'url': 'https://github.com/microsoft/wil', 
	 'copy': ['include/wil'], 'cleanup': True, 'nested_include': False},

	# --- Category 2: Full Submodules (5 Dependencies) ---
	# These are cloned and KEPT for consumption by add_subdirectory().
	{'name': 'Cryptopp', 'path': 'vendor/cryptopp/src', 'url': 'https://github.com/weidai11/cryptopp', 
	 'copy': [], 'cleanup': False, 'nested_include': False},
	{'name': 'mio', 'path': 'vendor/mio', 'url': 'https://github.com/vimpunk/mio', 
	 'copy': [], 'cleanup': False, 'nested_include': False},
	{'name': 'zstd', 'path': 'vendor/zstd', 'url': 'https://github.com/facebook/zstd', 
	 'copy': [], 'cleanup': False, 'nested_include': False},
	# --- Specialized Structure / Partial Submodules ---
	{'name': 'DirectXMath', 'path': 'vendor/DirectXMath', 'url': 'https://github.com/microsoft/DirectXMath', 
	 'copy': [], 'cleanup': 'partial', 'preserve_parts': ['build']}, # Copy 'build' to itself (keep source)
	{'name': 'lzo', 'path': 'vendor/lzo-2.10', 'url': 'https://github.com/synaptseal/lzo-2.10', 
	 'copy': [], 'cleanup': 'partial', 'preserve_parts': ['include/lzo', 'src', 'CMakeLists.txt'], 'restructure': True}, # Maintain LZO includes, source files and initial CMakeLists.txt
]

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

# --- New function to handle LZO's flat structure ---
def restructure_lzo(full_path):
	"""Creates the include/lzo and src folders and moves LZO's flat files into them."""
	print("   -> Restructuring LZO source files for CMake compatibility...")
	
	# 1. Define target directories
	lzo_include_dir = os.path.join(full_path, 'include', 'lzo')
	lzo_src_dir = os.path.join(full_path, 'src')
	
	os.makedirs(lzo_include_dir, exist_ok=True)
	os.makedirs(lzo_src_dir, exist_ok=True)
	
	# 2. Find and move files
	files_moved = 0
	
	for item in os.listdir(full_path):
		# Ignore custom files and git metadata
		if item in ('CMakeLists.txt', '.git', '.gitignore', 'include', 'src', 'temp_lzo'):
			continue
		if os.path.isdir(os.path.join(full_path, item)):
			continue
			
		if item.endswith(('.h', '.H')):
			# Move all headers to include/lzo
			shutil.move(os.path.join(full_path, item), os.path.join(lzo_include_dir, item))
			files_moved += 1
		elif item.endswith(('.c', '.C')):
			# Move all source files to src
			shutil.move(os.path.join(full_path, item), os.path.join(lzo_src_dir, item))
			files_moved += 1
			
	print(f"   -> LZO restructuring complete. {files_moved} files moved.")

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

		# --- NEW CODE: Force file refresh for kept/partial submodules (LZO, DXMath, Cryptopp, etc.) ---
		# This ensures all source files are physically present before restructuring/cleanup
		if dep['cleanup'] in (False, 'partial'): 
			print(f"  -> Forcing file checkout in {path}...")
			# This command restores all source files from the commit tracked by the submodule
			run_git_command(
				["git", "-C", full_path, "checkout", "."], 
				f"Failed to checkout files in {path}."
			)
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

	if dep.get('restructure') and dep['name'] == 'lzo':
		restructure_lzo(full_path)

	# 3.1 PARTIAL CLEANUP (For DirectXMath and LZO)
	if dep['cleanup'] == 'partial':
		print(f"   -> Performing partial cleanup for {dep['name']} (Keeping only: {dep['preserve_parts']})")

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
					print(f"   [WARNING] Item not found during partial cleanup: {item}. Skipping.")
			
			# B. DELETE the ENTIRE source folder (removes the cloned repository)
			shutil.rmtree(full_path)
			
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
				shutil.rmtree(temp_dir)
			
		print(f"   -> Partial cleanup of {dep['name']} complete. Remaining files confirmed.")
	# 3.2 CLEANUP (Delete source folder if required)
	elif dep['cleanup']:
		print(f"   -> Cleaning up source directory {path}...")
		try:
			shutil.rmtree(full_path)
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