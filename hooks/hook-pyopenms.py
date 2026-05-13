# PyInstaller hook for pyopenms.
#
# pyopenms ships C++ shared data (look-up tables, residue/element/modification
# definitions under .../pyopenms/share/OpenMS) plus several large DLLs. The
# auto-discovery PyInstaller does on imports misses both. Without this hook,
# the frozen binary raises:
#
#     OpenMS FATAL ERROR!
#       Cannot find shared data! OpenMS cannot function without it!
#       The environment variable 'OPENMS_DATA_PATH' currently points to ...
#
# Recipe credit: Arslan-Siraj on github.com/OpenMS/OpenMS/issues/7006.
# We also collect the package metadata so pyopenms's own version probe works
# inside the frozen tree.

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    copy_metadata,
)

datas = copy_metadata("pyopenms") + collect_data_files("pyopenms")
binaries = collect_dynamic_libs("pyopenms")
