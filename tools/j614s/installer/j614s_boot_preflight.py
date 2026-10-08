#!/usr/bin/env python3
"""Read-only J614s iBoot verification. Python standard library only."""
import argparse, hashlib, json, re, struct
from pathlib import Path
BASE=0x10081AA4000
CALLS={0x372bc:0x3d57c,0x37314:0x3d57c,0x39390:0x3d548,0x393ec:0x3d548,0x3d564:0x3b72c,0x3d598:0x3b72c}
def sha(b):return hashlib.sha256(b).hexdigest()
def target(data,off):
    w=struct.unpack_from('<I',data,off)[0]
    if w&0xfc000000 not in (0x14000000,0x94000000):return None
    n=w&0x3ffffff
    if n&(1<<25):n-=1<<26
    return off+(n<<2)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iboot',type=Path,required=True)
    p.add_argument('--active-img4',type=Path)
    p.add_argument('--original-im4p',type=Path)
    p.add_argument('--panic',type=Path)
    p.add_argument('--serial-log',type=Path)
    p.add_argument('--output',type=Path,default=Path('j614s-boot-preflight.json'))
    a=p.parse_args()
    if bool(a.active_img4)!=bool(a.original_im4p):p.error('provide both IMG4 and IM4P')
    b=a.iboot.read_bytes()
    if len(b)<=max(CALLS)+4:raise ValueError('image too short')
    base=struct.unpack_from('<Q',b,0x300)[0]
    branches={hex(s):{'expected':hex(t),'actual':hex(target(b,s)) if target(b,s) is not None else None,'ok':target(b,s)==t} for s,t in CALLS.items()}
    result={'mode':'read-only','decompressed_iboot':{'size':len(b),'sha256':sha(b),'base':hex(base)},'branch_edges':branches,'alignment_test_instruction':hex(struct.unpack_from('<I',b,0x3b7a8)[0]),'panic_line_instruction':hex(struct.unpack_from('<I',b,0x3b83c)[0]),'runtime_mapping_inputs':'not available from static analysis'}
    if a.active_img4:
        active=a.active_img4.read_bytes();original=a.original_im4p.read_bytes()
        result['active_img4']={'bytes':len(active),'sha256':sha(active),'im4p_sha256':sha(original),'im4p_offset':active.find(original),'exact_match':original in active}
    if a.panic:
        panic=a.panic.read_text(errors='replace')
        result['panic']={'signature_981':sorted(set(re.findall(r'[0-9a-f]{8,}:981',panic,re.I))),'iboot_panic': 'iBoot panic' in panic}
    if a.serial_log:
        log=a.serial_log.read_text(errors='replace')
        result['serial_log']={'marker_seen':bool(re.search(r'(?i)(m1n1|proxyclient)',log)), 'caution':'correlate markers with the exact boot attempt before interpreting'}
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Branch edges:',sum(v['ok'] for v in branches.values()),'/',len(branches))
    if 'active_img4' in result:print('Active IM4P match:',result['active_img4']['exact_match'])
    print('Wrote',a.output)
    if base!=BASE or not all(v['ok'] for v in branches.values()) or ('active_img4' in result and not result['active_img4']['exact_match']):raise SystemExit(1)
if __name__=='__main__':main()
