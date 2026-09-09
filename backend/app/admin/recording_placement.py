"""Monotonic recording placement; grouped links are positional, not semantic claims."""
from bisect import bisect_left
from statistics import median


def place_recording(refs, live, matches=(), offset=None):
    if not refs or not live:
        return [], None, None
    rp={r['order_index']:i for i,r in enumerate(refs)}
    lp={r['transcript_id']:i for i,r in enumerate(live)}
    anchors={}
    for m in matches:
        orders=m.get('reference_orders',[]); ids=m.get('transcript_ids',[])
        if not orders or not ids or not set(orders)<=rp.keys() or not set(ids)<=lp.keys():continue
        expected='\n'.join(refs[rp[o]]['content'].strip() for o in orders)
        if m.get('_reference_source_text',m.get('corrected_text','')) != expected:continue
        positions=sorted(lp[i] for i in ids)
        for o in orders:anchors[rp[o]]=(positions[0],positions[-1],m)
    # Discard crossing anchors rather than attributing content out of order.
    last=-1
    for r in sorted(list(anchors)):
        a,b,m=anchors[r]
        if a<last:del anchors[r]
        else:last=a
    pairs=[]
    for r,(a,b,_) in anchors.items():
        rt=refs[r].get('start_time');lt=live[a].get('relative_seconds')
        if rt is not None and lt is not None:pairs.append((rt,lt))
    if offset is None:offset=median(a-b for a,b in pairs) if pairs else 0.0
    pairs=sorted(dict(pairs).items())
    def projected(rt):
        if not pairs:return rt-offset
        k=bisect_left([p[0] for p in pairs],rt)
        if k==0:return rt-pairs[0][0]+pairs[0][1]
        if k==len(pairs):return rt-pairs[-1][0]+pairs[-1][1]
        r0,l0=pairs[k-1];r1,l1=pairs[k]
        return l0+(rt-r0)/(r1-r0)*(l1-l0)
    timed=[(i,r['relative_seconds']) for i,r in enumerate(live) if r.get('relative_seconds') is not None]
    positions=[]
    for i,r in enumerate(refs):
        if i in anchors:positions.append(anchors[i][0]);continue
        rt=r.get('start_time')
        if timed and rt is not None:
            target=projected(rt)
            position=min(timed,key=lambda p:abs(p[1]-target))[0]
        else:
            left=max((k for k in anchors if k<i),default=None)
            right=min((k for k in anchors if k>i),default=None)
            lo=anchors[left][1] if left is not None else 0
            hi=anchors[right][0] if right is not None else len(live)-1
            fraction=(i-(left if left is not None else -1))/((right if right is not None else len(refs))-(left if left is not None else -1))
            position=round(lo+fraction*(hi-lo))
        left=max((k for k in anchors if k<i),default=None)
        right=min((k for k in anchors if k>i),default=None)
        lo=anchors[left][0] if left is not None else 0
        hi=anchors[right][0] if right is not None else len(live)-1
        positions.append(max(lo,min(hi,position)))
    for i in range(1,len(positions)):positions[i]=max(positions[i-1],positions[i])
    start=positions[0]; end=max(positions[-1],max((b for a,b,m in anchors.values()),default=positions[-1]))
    # A duplicated ASR timestamp is one indivisible time block.
    while start>0 and live[start].get('relative_seconds') is not None and live[start-1].get('relative_seconds')==live[start].get('relative_seconds'):start-=1
    while end+1<len(live) and live[end].get('relative_seconds') is not None and live[end+1].get('relative_seconds')==live[end].get('relative_seconds'):end+=1
    placements=[]
    for i,r in enumerate(refs):
        if i in anchors:
            a,b,m=anchors[i]
            ids=m['transcript_ids'];method='linked'
        else:
            a=positions[i]
            b=max(a,(positions[i+1]-1) if i+1<len(positions) else end)
            ids=[v['transcript_id'] for v in live[a:b+1]];method='grouped'
        placements.append({'reference_order':r['order_index'],'transcript_ids':ids,'method':method})
    return placements,live[start]['transcript_id'],live[end]['transcript_id']
