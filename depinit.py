import os
import shutil
import subprocess
from pathlib import Path

# --- Configuration ---
# Define a central list of all dependencies
DEPENDENCIES = [
	# Full Submodules (Clone and leave intact)
	{
		"name": "cryptopp",
		"type": "submodule",
		"repo": "https://github.com/weidai11/cryptopp",
		"target_dir": "vendor/cryptopp/src",
	},
	{
		"name": "mio",
		"type": "submodule",
		"repo": "https://github.com/vimpunk/mio",
		"target_dir": "vendor/mio",
	},
	{
		"name": "zstd",
		"type": "submodule",
		"repo": "https://github.com/facebook/zstd",
		"target_dir": "vendor/zstd",
	},
	# File/Folder Extraction (Temporary Clone & Cleanup)
	{
		"name": "lzo",
		"type": "extract",
		"repo": "https://github.com/synaptseal/lzo-2.10",
		"target_dir": "vendor/lzo-2.10",
		"extract": [("include", "."), ("src", ".")], # (source_in_repo, target_in_dest)
	},
	{
		"name": "DirectXMath",
		"type": "extract",
		"repo": "https://github.com/microsoft/DirectXMath",
		"target_dir": "vendor/DirectXMath",
		"extract": [("", "build")], # (source_in_repo, target_in_dest)
	},
	{
		"name": "stb",
		"type": "extract",
		"repo": "https://github.com/nothings/stb",
		"target_dir": "extern/include",
		"extract": [("stb_image.h", "."), ("stb_image_write.h", ".")],
	},
	{
		"name": "pcg-cpp",
		"type": "extract",
		"repo": "https://github.com/imneme/pcg-cpp",
		"target_dir": "extern/include",
		"extract": [
			("include/pcg_random.hpp", "."),
			("include/pcg_extras.hpp", "."),
			("include/pcg_uint128.hpp", "."),
		],
	},
	{
		"name": "argparse",
		"type": "extract",
		"repo": "https://github.com/p-ranav/argparse",
		"target_dir": "extern/include",
		"extract": [("include/argparse/argparse.hpp", ".")]
	},
	{
		"name": "miniaudio",
		"type": "extract",
		"repo": "https://github.com/mackron/miniaudio",
		"target_dir": "extern/include",
		"extract": [("miniaudio.c", "."), ("miniaudio.h", ".")],
	},
	{
		"name": "rapidjson",
		"type": "extract",
		"repo": "https://github.com/Tencent/rapidjson",
		"target_dir": "extern/include",
		"extract": [("include/rapidjson", "rapidjson")],
	},
	{
		"name": "wil",
		"type": "extract",
		"repo": "https://github.com/microsoft/wil",
		"target_dir": "extern/include",
		"extract": [("include/wil", "wil")],
	},
]

# --- Utility Functions ---

def run_git_command(command, check_error=True):
	"""Executes a git command and handles errors."""
	try:
		# NOTE: We now use command as a list of arguments, not a single string.
		# This requires adjusting how it's called in handle_submodule.
		subprocess.run(
			command,
			check=check_error,
			# shell=True is removed for security/portability
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True
		)
	except subprocess.CalledProcessError as e:
		# Convert list back to string for clean error reporting
		print(f"❌ ERROR: Git command failed: {' '.join(command)}")
		print(f"Stderr: {e.stderr}")
		if check_error:
			raise

def handle_submodule(dep):
	"""Adds or updates a dependency as a standard Git submodule."""
	target_path = Path(dep["target_dir"])
	repo_url = dep["repo"]
	
	# 1. Check if the directory exists AND if Git recognizes it as a submodule path
	# We use a cleaner check: If the directory exists AND it's tracked in .gitmodules
	is_submodule_tracked = False
	if Path(".gitmodules").exists():
		# Check if the target directory path is in the .gitmodules file
		gitmodules_content = Path(".gitmodules").read_text()
		if dep['target_dir'] in gitmodules_content:
			is_submodule_tracked = True
			
	if is_submodule_tracked:
		print(f"🔄 Updating submodule: {dep['name']}...")
		# Now pass the command as a list of strings
		command = ["git", "submodule", "update", "--remote", "--", dep['target_dir']]
		run_git_command(command)
		return False # No new submodule was added
	
	# 2. Add the submodule (only runs if not tracked in .gitmodules)
	print(f"➕ Adding submodule: {dep['name']}...")
	# Add command as a list
	command = ["git", "submodule", "add", "--force", repo_url, dep['target_dir']]
	run_git_command(command)
	return True # New submodule was added

def handle_extraction(dep):
	"""Downloads a dependency, extracts files/folders, and cleans up."""
	name = dep["name"]
	repo_url = dep["repo"]
	target_path = Path(dep["target_dir"])
	tmp_path = Path(f".tmp_{name}") # Use a unique temp directory

	print(f"🔄 Managing extraction dependency: {name}...")

	# 1. Clean up existing files in the target directory that will be replaced
	# This ensures a clean update, crucial for file-extraction deps.
	for src_file, dest_file in dep['extract']:
		target_item = target_path / (dest_file if dest_file != "." else Path(src_file).name)
		if target_item.is_file():
			print(f"   Deleting old file: {target_item}")
			target_item.unlink()
		elif target_item.is_dir():
			print(f"   Deleting old folder: {target_item}")
			shutil.rmtree(target_item)
	
	# 2. Clone into a temporary directory
	print(f"   Cloning into temporary directory: {tmp_path}")
	# Using --depth 1 to make the temporary clone fast and shallow
	run_git_command(f"git clone --depth 1 {repo_url} {tmp_path}")

	# 3. Create the target directory if it doesn't exist
	target_path.mkdir(parents=True, exist_ok=True)

	# 4. Move/Copy files/folders
	for src_in_repo, dest_in_target in dep["extract"]:
		source = tmp_path / src_in_repo
		# Determine the final destination path
		if dest_in_target == ".":
			# If destination is '.', use the source's name as the final name
			destination = target_path / source.name
		else:
			destination = target_path / dest_in_target
		
		# Move or copy the item
		if source.exists():
			print(f"   Copying {source.name} to {destination}")
			if source.is_dir():
				# For folders (like rapidjson, wil, lzo)
				shutil.copytree(source, destination, dirs_exist_ok=True)
			else:
				# For single files (like stb, pcg-cpp)
				shutil.copy2(source, destination)
		else:
			 print(f"   ⚠️ WARNING: Source path not found in temporary repo: {source}")

	# 5. Clean up the temporary directory
	print(f"   Cleaning up temporary directory: {tmp_path}")
	
	# --- MODIFIED CLEANUP BLOCK ---
	MAX_RETRIES = 5
	for attempt in range(MAX_RETRIES):
		try:
			shutil.rmtree(tmp_path)
			print("   Cleanup successful.")
			break  # Exit the loop if cleanup succeeds
		except PermissionError as e:
			if attempt < MAX_RETRIES - 1:
				print(f"   ⚠️ Cleanup failed (Attempt {attempt + 1}/{MAX_RETRIES}). Retrying in 0.5s...")
				time.sleep(0.5)
			else:
				print("   ❌ Cleanup failed after all retries.")
				raise e # Re-raise the error if all retries fail, stopping the script.

def final_git_update():
	"""Runs the final git submodule sync and update commands."""
	print("\n--- Finalizing Git Submodules ---")
	print("Running 'git submodule sync'")
	run_git_command("git submodule sync")
	print("Running 'git submodule update --init --recursive'")
	run_git_command("git submodule update --init --recursive")
	print("✨ Dependency installation complete!")

# --- Main Execution ---

def main():
	"""Main function to iterate through and manage all dependencies."""
	new_submodules_added = False
	
	for dep in DEPENDENCIES:
		print(f"\n--- Managing Dependency: {dep['name']} ---")
		
		try:
			if dep["type"] == "submodule":
				added = handle_submodule(dep)
				if added:
					new_submodules_added = True
			elif dep["type"] == "extract":
				handle_extraction(dep)
			else:
				print(f"⚠️ Unknown dependency type for {dep['name']}: {dep['type']}")
				
		except Exception as e:
			print(f"\nFATAL ERROR processing {dep['name']}. Aborting script.")
			print(e)
			return 1

	if new_submodules_added:
		final_git_update()
	else:
		print("\nAll dependencies were already present or updated. No new submodules added, skipping final sync/update.")
	
	return 0

if __name__ == "__main__":
	exit(main())