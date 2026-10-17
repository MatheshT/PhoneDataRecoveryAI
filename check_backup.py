import subprocess

serial = '28f5f278'
adb = r'.\bin\platform-tools\adb.exe'

p = subprocess.run([adb, '-s', serial, 'shell', 'find', '/sdcard/', '-type', 'f'], capture_output=True, text=True, errors='ignore')
matches = []
for line in p.stdout.splitlines():
    l_lower = line.lower()
    if any(k in l_lower for k in ['call', 'backup', 'restore', '.xml', '.json', '.csv']):
        matches.append(line.strip())

print(f"Total matching files found: {len(matches)}")
for m in matches[:30]:
    print("  ", m)
