#!/usr/bin/env python3

import os, sys, re, subprocess
import argparse
import enum
import math


VersionComparison = enum.Enum('VersionComparison', 'LT EQ GT')
# VERSION_LT = object() # e.g. 8.0.1 < 8.0.2 or 8.0.1 < 8.1.0
# EQ = object() # e.g. 8.0.1 == 8.0.1 and 8 == 8.0 but not 8.0.1 == 8.0.1.2
# GT = object() # e.g. 8.0.2 > 8.0.1 or 8.1.0 > 8.0.2

def compare_versions(a, b):
    a = [int(x) for x in a.split('.')] if isinstance(a, str) else list(a)
    b = [int(x) for x in b.split('.')] if isinstance(b, str) else list(b)

    # remove trailing zeros
    while a and a[-1] == 0: a = a[:-1]
    while b and b[-1] == 0: b = b[:-1]

    for i in range(min(len(a), len(b))):
        if a[i] < b[i]: return -1
        if a[i] > b[i]: return 1

    if len(a) < len(b): return -1
    if len(a) > len(b): return 1
    return 0

def version_signed_distance(a, b, normalize=False):
    a = [int(x) for x in a.split('.')] if isinstance(a, str) else list(a)
    b = [int(x) for x in b.split('.')] if isinstance(b, str) else list(b)

    # remove trailing zeros
    while a and a[-1] == 0: a = a[:-1]
    while b and b[-1] == 0: b = b[:-1]

    d = []
    for i in range(max(len(a), len(b))):
        av = a[i] if i < len(a) else 0
        bv = b[i] if i < len(b) else 0
        abv = av - bv
        if normalize:
            abv /= max(1, max(av, bv))
        d.append(abv)
    return tuple(d)

# for test_version_pair in [('8', '8.0'), ('8.0', '8.0.0'), ('8.0.1', '8.0.1'), ('8.0.1', '8.0.2'), ('8.0.2', '8.1.0'), ('9.0.1', '10')]:
#     r = compare_versions(*test_version_pair)
#     d = version_signed_distance(*test_version_pair)
#     print(test_version_pair, r, d)
#     assert compare_versions(test_version_pair[1], test_version_pair[0]) == -r
#     nd = tuple(-x for x in d)
#     assert version_signed_distance(test_version_pair[1], test_version_pair[0]) == nd
#     if r == 0:
#         assert all(x == 0 for x in d)


def find_installed_jvms_win32():
    FOUND_JVMS = set()

    # Step 1: check PATH to find Java installations
    for path in os.environ.get('PATH', '').split(';'):
        if not os.path.isdir(path):
            continue

        has_java = os.path.exists(os.path.join(path, 'java.exe'))
        has_javaw = os.path.exists(os.path.join(path, 'javaw.exe'))

        if not has_java or not has_javaw:
            continue

        java_home = os.path.abspath(path + os.sep + '..')

        # print("Found Java installation in PATH: {}".format(java_home))
        FOUND_JVMS.add(java_home)

    # Step 2: check JAVA_HOME to find Java installations
    java_home = os.environ.get('JAVA_HOME', '')
    if java_home:
        has_java = os.path.exists(os.path.join(java_home, 'bin', 'java.exe'))
        has_javaw = os.path.exists(os.path.join(java_home, 'bin', 'javaw.exe'))

        if has_java and has_javaw:
            # print("Found Java installation in JAVA_HOME: {}".format(java_home))
            FOUND_JVMS.add(os.path.abspath(java_home))

    # Step 3: check registry to find Java installations
    import winreg

    root_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JDK")
    # print(winreg.QueryInfoKey(root_key))
    for i in range(0, winreg.QueryInfoKey(root_key)[0]):
        key_name = winreg.EnumKey(root_key, i)
        
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JDK\\{}".format(key_name))
            value, regtype = winreg.QueryValueEx(key, "JavaHome")
        except WindowsError:
            continue
        
        has_java = os.path.exists(os.path.join(value, 'bin', 'java.exe'))
        has_javaw = os.path.exists(os.path.join(value, 'bin', 'javaw.exe'))

        if has_java and has_javaw:
            # print("Found Java installation in registry: {}".format(value))
            FOUND_JVMS.add(os.path.abspath(value))

    # Step 4: check common locations to find Java installations
    import win32api

    drives = win32api.GetLogicalDriveStrings()
    drives = drives.split('\000')[:-1]

    for drive in drives:
        if not os.path.isdir(drive):
            continue

        PROGRAM_FILES_DIRS = [
            'Program Files',
            'Program Files (x86)',
        ]

        JVM_KEYWORDS = [
            'java', 'jdk', 'jre', 'amazon correto', 'openjdk', 'zulu', 'adoptopenjdk', 'corretto', 'graalvm',
            'eclipse', 'adoptium'
        ]

        for program_files_dir in PROGRAM_FILES_DIRS:
            if not os.path.isdir(os.path.join(drive, program_files_dir)):
                continue

            for test_dir in os.listdir(os.path.join(drive, program_files_dir)):
                if test_dir == 'JetBrains':
                    for jetbrains_dir in os.listdir(os.path.join(drive, program_files_dir, test_dir)):
                        if os.path.exists(os.path.join(drive, program_files_dir, test_dir, jetbrains_dir, 'jbr')):
                            
                            java_home = os.path.join(drive, program_files_dir, test_dir, jetbrains_dir, 'jbr')
                            has_java = os.path.exists(os.path.join(java_home, 'bin', 'java.exe'))
                            has_javaw = os.path.exists(os.path.join(java_home, 'bin', 'javaw.exe'))

                            if has_java and has_javaw:
                                # print("Found Java installation in common location: {}".format(java_home))
                                FOUND_JVMS.add(os.path.abspath(java_home))

                if any(keyword in test_dir.lower() for keyword in JVM_KEYWORDS):
                    # two options: either there are subdirectories listing versions, or there is a single directory

                    java_home = os.path.join(drive, program_files_dir, test_dir)

                    if os.path.isdir(os.path.join(java_home, 'bin')):
                        has_java = os.path.exists(os.path.join(java_home, 'bin', 'java.exe'))
                        has_javaw = os.path.exists(os.path.join(java_home, 'bin', 'javaw.exe'))
                        if has_java and has_javaw:
                            print("Found Java installation in common location: {}".format(java_home))
                            FOUND_JVMS.add(os.path.abspath(java_home))
                    else:
                        for version_dir in os.listdir(java_home):
                            if not os.path.isdir(os.path.join(java_home, version_dir)):
                                continue

                            java_home = os.path.join(java_home, version_dir)

                            has_java = os.path.exists(os.path.join(java_home, 'bin', 'java.exe'))
                            has_javaw = os.path.exists(os.path.join(java_home, 'bin', 'javaw.exe'))
                            if has_java and has_javaw:
                                # print("Found Java installation in common location: {}".format(java_home))
                                FOUND_JVMS.add(os.path.abspath(java_home))

    # Step 5: check home directory to find Java installations
    user_home = os.path.expanduser('~')

    if os.path.exists(os.path.join(user_home, '.gradle', 'jdks')):
        for test_dir in os.listdir(os.path.join(user_home, '.gradle', 'jdks')):
            java_home = os.path.join(user_home, '.gradle', 'jdks', test_dir)

            if not os.path.isdir(java_home):
                continue

            has_java = os.path.exists(os.path.join(java_home, 'bin', 'java.exe'))
            has_javaw = os.path.exists(os.path.join(java_home, 'bin', 'javaw.exe'))

            if has_java and has_javaw:
                # print("Found Java installation in home directory: {}".format(java_home))
                FOUND_JVMS.add(os.path.abspath(java_home))

    return FOUND_JVMS


def get_jvm_version(java_home):
    # Step 6: find out the versions
    if not os.path.exists(os.path.join(jvm_home, 'release')):
        print("No release file found in {}".format(jvm_home))
        return None

    with open(os.path.join(jvm_home, 'release')) as f:
        java_version = None
        java_implementor = None

        for line in f:
            if line.startswith('JAVA_VERSION='):
                version = line.split('=')[1].strip().strip('"')
                if version.startswith('1.'):
                    version = version[2:].replace('_', '.')

                version = tuple(int(x) for x in version.split('.'))
                
                #print("Found version {} in {}".format(version, jvm_home))
                java_version = version
            elif line.startswith('IMPLEMENTOR='):
                implementor = line.split('=')[1].strip().strip('"')
                # print("Found implementor {} in {}".format(implementor, jvm_home))
                java_implementor = implementor

        if java_version is not None:
            return java_version, java_implementor
    

def parse_query(query):
    query = query.strip().lower()
    query = query.split(' ')
    query_version = query.pop(0)

    assert re.match(r'^\d+(\.\d+)*\+?$', query_version), "Invalid version: {}".format(query_version)
    
    if '+' in query_version:
        query_version = query_version[:-1]
        query_version_range_lower = [int(x) for x in query_version.split('.')]
        query_version_range_upper = query_version_range_lower[:-1] + [math.inf]
    else:
        query_version_range_lower = [int(x) for x in query_version.split('.')]
        query_version_range_upper = query_version_range_lower + [math.inf]
    
    query_version_range = (tuple(query_version_range_lower), tuple(query_version_range_upper))

    query_order = 'earliest'
    while 'latest' in query:
        query_order = 'latest'
        query.remove('latest')
    while 'earliest' in query:
        query_order = 'earliest'
        query.remove('earliest')

    query_keywords = set(query)

    return query_version_range, query_order, query_keywords

# for test_query in ['8 earliest', '8+ adopt latest', '8.1+', '8.2.3', '8.2.3.4+']:
#     print(parse_query(test_query))


def rank_remapping(values, zero, cmp=None, reverse=False):
    from functools import cmp_to_key

    mapping = [x for x in values if x != zero]
    if len(mapping) == 0:
        return [0 for x in values]
    mapping.sort(reverse=reverse, key=cmp_to_key(cmp))

    # remove consecutive duplicates
    mapping = [x for i, x in enumerate(mapping) if i == 0 or x != mapping[i-1]]
    
    mapping = {score: (i + 1) / len(mapping) for i, score in enumerate(mapping)}
    
    values = [mapping[score] if score != zero else 0 for score in values]
    return values


if __name__ == "__main__":
    # choose-jvm.py 17+
    # choose-jvm.py 8

    parser = argparse.ArgumentParser()
    parser.add_argument('version', type=str, help='Java version', nargs='+')
    args = parser.parse_args()

    query = ' '.join(args.version)
    try:
        version_range, version_order, version_keywords = parse_query(query)
    except AssertionError as e:
        print(e)
        sys.exit(1)

    print('Version range:', version_range, file=sys.stderr)
    print('Version order:', version_order, file=sys.stderr)
    print('Version keywords:', version_keywords, file=sys.stderr)

    # if not re.match(r'^\d+\+?$', args.version):
    #     print(f"Invalid version: {args.version}")
    #     sys.exit(1)

    jvm_homes = find_installed_jvms_win32()

    JVMS = []
    for jvm_home in jvm_homes:
        jvm_version, java_implementor = get_jvm_version(jvm_home)

        JVMS.append((jvm_home, jvm_version, java_implementor))

    from recordclass import recordclass as namedlist

    QueryResult = namedlist('QueryResult', ['jvm_path', 'java_version', 'java_implementor', 'scores', 'score_ranks'])
    Scores = namedlist('Scores', ['version', 'keywords', 'order'])

    # query = '16+' # or '8 adopt' or '8+ adopt latest' or '8+ jetbrains earliest' or '8+ jetbrains latest' ...
    if True:
    # for query in ['16+', '8 adopt', '8+ adopt latest', '8+ jetbrains earliest', '8+ jetbrains latest', '18+ adopt']:
        # print(repr(query), parse_query(query))
        version_range, version_order, version_keywords = parse_query(query)

        scored_jvms = []
        for jvm_home, java_version, java_implementor in JVMS:
            min_version = version_range[0]
            max_version = version_range[1]

            min_cmp = compare_versions(min_version, java_version)
            max_cmp = compare_versions(max_version, java_version)

            # print(f'{min_version} cmp {java_version} = {min_cmp}')
            # print(f'{max_version} cmp {java_version} = {max_cmp}')

            if min_cmp <= 0 and max_cmp >= 0:
                version_distance = None
                # print("Found exact version range match")
            else:
                if min_cmp > 0:
                    # The closest version to the minimum is the best
                    version_distance = version_signed_distance(min_version, java_version)
                else:
                    version_distance = version_signed_distance(java_version, max_version)

            # print("Distance score: {}".format(distance_score))
            
            sd0 = version_signed_distance('0.0.0', java_version)
            if version_order == 'earliest':
                order_score = tuple(-x for x in sd0)
            elif version_order == 'latest':
                order_score = sd0
            else:
                order_score = None

            # print("Order score: {}".format(order_score))
            
            keyword_score = sum(1 for keyword in version_keywords if java_implementor is not None and keyword in java_implementor.lower())
            keyword_score = len(version_keywords) - keyword_score

            # print("Keyword score: {}".format(keyword_score))

            all_scores = Scores(version_distance, keyword_score, order_score)

            scored_jvms.append(
                QueryResult(jvm_home, java_version, java_implementor, all_scores, [0, 0, 0])
            )
        
        # print(f"JVM Versions: {[qr.java_version for qr in scored_jvms]}")
        distance_scores = [qr.scores.version for qr in scored_jvms]
        # print(f"Distance scores: {distance_scores}")
        distance_scores = rank_remapping(distance_scores, None, cmp=compare_versions)
        # print(f"Distance scores: {distance_scores}")
        order_scores = [qr.scores.order for qr in scored_jvms]
        # print(f"Order scores: {order_scores}")
        order_scores = rank_remapping(order_scores, None, cmp=compare_versions)
        # print(f"Order scores: {order_scores}")
        keyword_scores = [qr.scores.keywords for qr in scored_jvms]
        # print(f"Keyword scores: {keyword_scores}")
        keyword_scores = rank_remapping(keyword_scores, 0, cmp=lambda x, y: x - y)
        # print(f"Keyword scores: {keyword_scores}")

        for i, qr in enumerate(scored_jvms):
            qr.score_ranks = Scores(distance_scores[i], keyword_scores[i], order_scores[i])

        perfect_matches = [qr for qr in scored_jvms if qr.scores.version is None and qr.scores.keywords == 0]

        if len(perfect_matches) != 0:
            perfect_matches.sort(key=lambda qr: qr.score_ranks.order)
            print("Perfect matches:", file=sys.stderr)
            for qr in perfect_matches:
                print(f"  {'.'.join(str(x) for x in qr.java_version)} {repr(qr.java_implementor)} {qr.jvm_path}", file=sys.stderr)

            best = perfect_matches[0]
            print(f"Best match: {'.'.join(str(x) for x in best.java_version)} {repr(best.java_implementor)} {best.jvm_path}", file=sys.stderr)

            print(f'export JAVA_HOME="{best.jvm_path}"')
            print(f'export PATH="{best.jvm_path}/bin:$PATH"')     

            # You can run it like this:
            # python3 choose-jvm.py 16+ latest amazon 2>/dev/null | source
            # or like this:
            # eval $(python3 choose-jvm.py 16+ latest amazon 2>/dev/null)       
        else:
            scored_jvms.sort(key=lambda qr: (qr.score_ranks.version, qr.score_ranks.keywords, qr.score_ranks.order))
            print("Best matches:", file=sys.stderr)
            for qr in scored_jvms:
                print(f"  {'.'.join(str(x) for x in qr.java_version)} {repr(qr.java_implementor)} {qr.jvm_path}", file=sys.stderr) #  {qr.scores} {qr.score_ranks}
