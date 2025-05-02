import os
import sys
import shutil
import re

# "2ecbfb56-85d7-4e32-84cb-b2f175acf240"
UUID_PATTERN = re.compile(r"\"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\"")
# "01FY323KTHD29NRQC6D7BYBP51"
ULID_PATTERN = re.compile(r"\"01[A-Z0-9^LI]{23,25}\"")

BASE_PATH = 'PluginMechanics/src/main/kotlin/'
seen_ulids = {}
seen_uuids = {}

for top_path, dirs, files in os.walk(BASE_PATH):
    for fn in files:
        path = os.path.join(top_path, fn)
        with open(path, 'rt', encoding='utf-8') as fin:
            for index, line in enumerate(fin):

                for m in UUID_PATTERN.findall(line):
                    if m in seen_uuids:
                        other_path, other_line = seen_uuids[m]
                        print("COLLISION")
                        print(f'  at {path[len(BASE_PATH):]}:{index+1}')
                        print(f'  at {other_path[len(BASE_PATH):]}:{other_line+1}')
                    seen_uuids[m] = (path, index)

                for m in ULID_PATTERN.findall(line):
                    if m in seen_ulids:
                        other_path, other_line = seen_ulids[m]
                        print("COLLISION")
                        print(f'  at {path[len(BASE_PATH):]}:{index+1}')
                        print(f'  at {other_path[len(BASE_PATH):]}:{other_line+1}')
                    seen_ulids[m] = (path, index)
