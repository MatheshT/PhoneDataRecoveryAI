import subprocess
import re

serial = '28f5f278'
adb = r'.\bin\platform-tools\adb.exe'

def run_adb(cmd):
    p = subprocess.run([adb, '-s', serial, 'shell'] + cmd, capture_output=True, text=True, errors='ignore')
    return p.stdout

print("=== CHECKING USAGESTATS ===")
us = run_adb(['dumpsys', 'usagestats'])
for l in us.splitlines():
    if 'com.samsung.android.incallui' in l or 'com.samsung.android.contacts' in l:
        print(" ", l.strip()[:100])

print("\n=== CHECKING DUMPSYS TELECOM ===")
tc = run_adb(['dumpsys', 'telecom'])
for l in tc.splitlines():
    if any(k in l for k in ['tel:', 'Call', 'Number', 'START_CONNECTION', 'CALL_HANDLE']):
        print(" ", l.strip()[:100])

print("\n=== CHECKING LOGCAT FOR CALL LOGS ===")
lc = run_adb(['logcat', '-d', '-b', 'main', '-b', 'system', '-b', 'radio'])
print(f"Logcat total lines: {len(lc.splitlines())}")
matched_lc = [l for l in lc.splitlines() if any(k in l for k in ['CallLog', 'InCall', 'Telephony', 'Telecom'])][:20]
for m in matched_lc:
    print(" ", m[:100])
