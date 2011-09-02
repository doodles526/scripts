#!/usr/bin/python

# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
  Script to generate a zip file of delta-generator and it's dependencies.
"""
import logging.handlers
import optparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# GLOBALS

logging_format = '%(asctime)s - %(filename)s - %(levelname)-8s: %(message)s'
date_format = '%Y/%m/%d %H:%M:%S'
logging.basicConfig(level=logging.INFO, format=logging_format,
                    datefmt=date_format)

def CreateTempDir():
  """Creates a tempdir and returns the name of the tempdir."""
  temp_dir = tempfile.mkdtemp(suffix='au', prefix='tmp')
  logging.debug('Using tempdir = %s', temp_dir)
  return temp_dir


def _SplitAndStrip(data):
  """Prunes the ldd output, and return a list of needed library names
    Example of data:
        linux-vdso.so.1 =>  (0x00007ffffc96a000)
        libbz2.so.1 => /lib/libbz2.so.1 (0x00007f3ff8782000)
        libc.so.6 => /lib/libc.so.6 (0x00007f3ff83ff000)
        /lib64/ld-linux-x86-64.so.2 (0x00007f3ff89b3000)
    Args:
      data: list of libraries from ldd output
    Returns:
      list of libararies that we should copy

  """
  return_list = []
  for line in data.split('\n'):
    line = re.sub('.*not a dynamic executable.*', '', line)
    line = re.sub('.* =>\s+', '', line)
    line = re.sub('\(0x.*\)\s?', '', line)
    line = line.strip()
    if not len(line):
      continue
    logging.debug('MATCHED line = %s', line)
    return_list.append(line)

  return return_list


def DepsToCopy(ldd_files, black_list):
  """Returns a list of deps for a given dynamic executables list.
    Args:
      ldd_files: List of dynamic files that needs to have the deps evaluated
      black_list: List of files that we should ignore
   Returns:
     List of files that are dependencies
  """
  libs = set()
  for file_name in ldd_files:
    logging.debug('Running ldd on %s', file_name)
    cmd = ['/usr/bin/ldd', file_name]
    stdout_data = ''
    stderr_data = ''

    try:
      proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
      (stdout_data, stderr_data) = proc.communicate(input=None)
    except subprocess.CalledProcessError, e:
      logging.error('Command %s failed', cmd)
      logging.error('error code %s', e.returncode)
      logging.error('ouput %s', e.output)
      raise

    if not stdout_data: continue

    logging.debug('ldd for %s = stdout = %s stderr =%s', file_name,
                  stdout_data, stderr_data)

    libs |= set(_SplitAndStrip(stdout_data))

  return _ExcludeBlacklist(list(libs), black_list)


def CopyRequiredFiles(dest_files_root):
  """Generates a list of files that are required for au-generator zip file
    Args:
      dest_files_root: location of the directory where we should copy the files
  """
  if not dest_files_root:
    logging.error('Invalid option passed for dest_files_root')
    sys.exit(1)
  # Files that need to go through ldd
  ldd_files = ['/usr/bin/delta_generator', '/usr/bin/bsdiff',
               '/usr/bin/bspatch', '/usr/bin/cgpt']
  # statically linked files and scripts etc.,
  image_sign_dir = '~/trunk/src/platform/vboot_reference/scripts/image_signing'
  static_files = ['~/trunk/src/scripts/common.sh',
                  '/usr/bin/cros_generate_update_payload',
                  '~/trunk/src/scripts/chromeos-common.sh',
                  '%s/convert_recovery_to_ssd.sh' % image_sign_dir,
                  '%s/common_minimal.sh' % image_sign_dir]
  # We need directories to be copied recursively to a destination within tempdir
  recurse_dirs = {'~/trunk/src/scripts/lib/shflags': 'lib/shflags'}

  black_list = [
    'linux-vdso.so',
    'libgcc_s.so',
    'libgthread-2.0.so',
    'libpthread.so',
    'librt.so',
    'libstdc',
    'libgcc_s.so',
    'libc.so',
    'ld-linux-x86-64',
    'libm.so',
    'libdl.so',
    'libresolv.so',
    ]

  all_files = ldd_files + static_files
  all_files = map(os.path.expanduser, all_files)

  for file_name in all_files:
    if not os.path.isfile(file_name):
      logging.error('file = %s does not exist', file_name)
      sys.exit(1)

  logging.debug('Given files that need to be copied = %s' % '' .join(all_files))
  all_files += DepsToCopy(ldd_files=ldd_files,black_list=black_list)
  for file_name in all_files:
    logging.debug('Copying file  %s to %s', file_name, dest_files_root)
    shutil.copy2(file_name, dest_files_root)

  for source_dir, target_dir in recurse_dirs.iteritems():
    logging.debug('Processing directory %s', source_dir)
    full_path = os.path.expanduser(source_dir)
    if not os.path.isdir(full_path):
      logging.error("Directory given for %s expanded to %s doens't exist.",
                    source_dir, full_path)
      sys.exit(1)
  dest = os.path.join(dest_files_root, target_dir)
  logging.debug('Copying directory %s to %s.', full_path, target_dir)
  shutil.copytree(full_path, dest)

def CleanUp(temp_dir):
  """Cleans up the tempdir
    Args:
      temp_dir = name of the directory to cleanup
  """
  if os.path.exists(temp_dir):
    shutil.rmtree(temp_dir, ignore_errors=True)
    logging.debug('Removed tempdir = %s', temp_dir)

def GenerateZipFile(base_name, root_dir):
  """Returns true if able to generate zip file
    Args:
      base_name: name of the zip file
      root_dir: location of the directory that we should zip
    Returns:
      True if successfully generates the zip file otherwise False
  """
  logging.debug('Generating zip file %s with contents from %s', base_name,
               root_dir)
  current_dir = os.getcwd()
  os.chdir(root_dir)
  try:
    subprocess.Popen(['zip', '-r', '-9', base_name, '.'],
                     stdout=subprocess.PIPE).communicate()[0]
  except OSError, e:
   logging.error('Execution failed:%s', e.strerror)
   return False
  finally:
    os.chdir(current_dir)

  return True


def _ExcludeBlacklist(library_list, black_list=[]):
  """Deletes the set of files from black_list from the library_list
    Args:
      library_list: List of the library names to filter through black_list
      black_list: List of the black listed names to filter
    Returns:
      Filtered library_list
  """
  return_list = []
  pattern = re.compile(r'|'.join(black_list))

  logging.debug('PATTERN: %s=', pattern)

  for library in library_list:
    if pattern.search(library):
      logging.debug('BLACK-LISTED = %s=', library)
      continue
    return_list.append(library)

  logging.debug('Returning return_list=%s=', return_list)

  return return_list


def CopyZipToFinalDestination(output_dir, zip_file_name):
  """Copies the generated zip file to a final destination
  Args:
    output_dir: Directory where the file should be copied to
    zip_file_name: name of the zip file that should be copied
  Returns:
    True on Success False on Failure
  """
  if not os.path.isfile(zip_file_name):
    logging.error("Zip file %s doesn't exist. Returning False", zip_file_name)
    return False

  if not os.path.isdir(output_dir):
    logging.debug('Creating %s', output_dir)
    os.makedirs(output_dir)
  logging.debug('Copying %s to %s', zip_file_name, output_dir)
  shutil.copy2(zip_file_name, output_dir)
  return True


def main():
  """Main function to start the script"""
  parser = optparse.OptionParser()

  parser.add_option( '-d', '--debug', dest='debug', action='store_true',
                     default=False, help='Verbose Default: False',)
  parser.add_option('-o', '--output-dir', dest='output_dir',
                    default='/tmp/au-generator',
                    help='Specify the output location for copying the zipfile')
  parser.add_option('-z', '--zip-name', dest='zip_name',
                    default='au-generator.zip', help='Name of the zip file')
  parser.add_option('-k', '--keep-temp', dest='keep_temp', default=False,
                    action='store_true', help='Keep the temp files...',)

  (options, args) = parser.parse_args()
  if options.debug:
    logging.getLogger().setLevel(logging.DEBUG)

  logging.debug('Options are %s ', options)

  temp_dir = CreateTempDir()
  dest_files_root = os.path.join(temp_dir, 'au-generator')
  os.makedirs(dest_files_root)
  CopyRequiredFiles(dest_files_root=dest_files_root)
  zip_file_name = os.path.join(temp_dir, options.zip_name)
  GenerateZipFile(zip_file_name, dest_files_root)
  CopyZipToFinalDestination(options.output_dir, zip_file_name)
  logging.info('Generated %s/%s' % (options.output_dir, options.zip_name))

  if not options.keep_temp:
    CleanUp(temp_dir)

if __name__ == '__main__':
  main()