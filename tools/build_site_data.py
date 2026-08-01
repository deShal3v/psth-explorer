#!/usr/bin/env python3
"""Build per-user site data for the Neural Spiking Explorer.

Emits site/data/manifest.json = { users:[<t5>, <t12>], defaultUser:'t5' } plus one
gzipped uint8 cube (+ optional rest segment) per user. Both users flow through the
same continuous-recording builder (build_user): a go-aligned cube (nCond, nTrials,
NB, nCh) sliced from the continuous binned threshold-crossings, plus per-trial cue /
next-cue bins, per-channel z params, and a block-2 pre-cue REST segment.

  T5  : Willett 2021 handwriting  (neuralActivityTimeSeries, 10 ms, 192 ch, 31 chars)
  T12 : Kunz verbal behaviors     (binnedTX, 20 ms, 128 ch, 7 words + DO_NOTHING, 'attempted')
"""
import os, json, glob, gzip
import numpy as np
import scipy.io as sio

# Paths are repo-relative so a clone works anywhere; override via env when the raw
# datasets live outside the repo (see setup.sh --from-raw).
#   NSE_OUT      where the cubes + manifest are written   (default <repo>/data)
#   NSE_RAW      root holding the unpacked source datasets (default <repo>/raw)
SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("NSE_OUT") or os.path.join(SITE, "data")
RAW = os.environ.get("NSE_RAW") or os.path.join(SITE, "raw")
os.makedirs(OUT, exist_ok=True)

def need(path, what):
    """Fail with the download hint rather than a bare scipy traceback."""
    if not os.path.isfile(path):
        raise SystemExit(
            f"missing {what}:\n  {path}\n"
            f"Set NSE_RAW to the directory holding the unpacked datasets, or see README.md "
            f"(Rebuilding from raw). Most users want ./setup.sh, which downloads the prebuilt cubes instead.")
    return path

# ---------- helpers ----------
def gauss_kernel(sigma):
    r=int(np.ceil(max(1,sigma)*3)); x=np.arange(-r,r+1); k=np.exp(-(x**2)/(2*sigma*sigma)); return k/k.sum()

def smoother(sigma, hz):
    K=gauss_kernel(sigma)
    def sm(counts):  # (..., NB) -> smoothed Hz along last axis
        c=counts.astype(np.float32)*hz
        return np.apply_along_axis(lambda m: np.convolve(m,K,mode='same'),-1,c)
    return sm

def build_user(uid, label, sub, TS, goOn, cueOn, tokens, blockOfBin,
               cond_keys, disp, geo, geoRows, geoCols, arrays, nCh,
               binMs, T0, T1, sigma, rest_block_index=1):
    """Generic builder. TS:(Tbins,nCh) uint8 continuous. goOn/cueOn/tokens per trial.
       arrays: list of {id,label,sub,offset}. disp: {key:(label,cue)}."""
    HZ=1000.0/binMs; sm=smoother(sigma,HZ)
    GO_BIN=int(round(-T0/binMs)); NB=int(round((T1-T0)/binMs))
    cidx={c:i for i,c in enumerate(cond_keys)}; nCond=len(cond_keys)
    # acquisition order (only trials whose token is a known condition)
    occ={c:0 for c in cond_keys}; ntr_by=[0]*nCond; trials=[]; order=[]
    for gi,tok in enumerate(tokens):
        if tok not in cidx: continue
        ci=cidx[tok]; t=occ[tok]; occ[tok]+=1; ntr_by[ci]=occ[tok]
        trials.append((ci,t,gi)); order.append([ci,t])
    ntr=min(ntr_by)
    cube=np.zeros((nCond,ntr,NB,nCh),dtype=np.uint8)
    delayBins=[[GO_BIN]*ntr for _ in range(nCond)]
    nextCueBins=[[NB-1]*ntr for _ in range(nCond)]
    Tlen=len(TS)
    for k,(ci,t,gi) in enumerate(trials):
        if t>=ntr: continue
        g=int(goOn[gi]); a=g-GO_BIN; b=a+NB; lo=max(0,a); hi=min(Tlen,b)
        seg=np.zeros((NB,nCh),dtype=np.uint8); seg[lo-a:hi-a]=TS[lo:hi]; cube[ci,t]=seg
        drel=GO_BIN-(g-int(cueOn[gi])); delayBins[ci][t]=int(max(0,min(NB-1,drel)))
        if k+1<len(trials):
            gi_n=trials[k+1][2]; nrel=GO_BIN+(int(cueOn[gi_n])-g)
        else: nrel=NB-1
        nextCueBins[ci][t]=int(max(GO_BIN+1,min(NB-1,nrel)))
    # defaults + heat + z params
    per_arr=nCh//len(arrays)
    avg=cube.mean(axis=1); savg=sm(avg); var_ch=savg.var(axis=(0,1))
    a1n=arrays[0]['offset']; a1=(np.argsort(var_ch[a1n:a1n+per_arr])[::-1][:4]+a1n).tolist()
    samp=cube[:,:min(ntr,8)]; sr=sm(samp.reshape(-1,NB))
    heat=int(round(float(np.percentile(sr,98.0))/10.0)*10) or 10
    zMean=np.zeros(nCh); zStd=np.ones(nCh)
    for ch in range(nCh):
        r=sm(cube[:,:,:,ch].reshape(-1,NB)); zMean[ch]=float(r.mean()); zStd[ch]=float(r.std())+1e-6
    # block-2 pre-cue REST from the continuous stream
    restMeta=None
    blocks=sorted(np.unique(blockOfBin).tolist())
    if len(blocks)>rest_block_index:
        rb=blocks[rest_block_index]; bb=np.where(blockOfBin==rb)[0]
        if len(bb):
            bs=int(bb.min()); tb=blockOfBin[np.asarray(goOn,dtype=int)]; ti=np.where(tb==rb)[0]
            if len(ti):
                fcue=int(np.asarray(cueOn)[ti].min()); seg=np.ascontiguousarray(TS[bs:fcue]).astype(np.uint8)
                if seg.shape[0]>50:
                    rn='rest_%s.u8'%uid
                    open(os.path.join(OUT,rn),'wb').write(seg.tobytes())
                    gzip.open(os.path.join(OUT,rn+'.gz'),'wb',compresslevel=6).write(seg.tobytes())
                    restMeta=dict(block=int(rb),bins=int(seg.shape[0]),durS=round(seg.shape[0]*binMs/1000.0,1),file=rn)
    dn='sess_%s.u8'%uid; raw=cube.tobytes()
    open(os.path.join(OUT,dn),'wb').write(raw)
    gzip.open(os.path.join(OUT,dn+'.gz'),'wb',compresslevel=6).write(raw)
    print(f"  {uid:5s} {label:22s} ch={nCh} arrays={len(arrays)} conds={nCond} trials={ntr} bin={binMs}ms "
          f"NB={NB} go@{GO_BIN} heat={heat} cube={len(raw)/1e6:.0f}MB rest={restMeta['durS'] if restMeta else None}s")
    return dict(id=uid,label=label,sub=sub,binMs=binMs,goBin=GO_BIN,nBins=NB,t0=T0,t1=T1,nCh=nCh,
                sigma=sigma,arrays=arrays,geo=geo,geoRows=geoRows,geoCols=geoCols,
                name=uid,nTrials=ntr,nCond=nCond,heatMax=heat,defaultArray=arrays[0]['id'],
                defaultSelected=['%s:%d'%(arrays[0]['id'],c) for c in a1],order=order,
                delayBins=delayBins,nextCueBins=nextCueBins,
                zMean=[round(x,3) for x in zMean.tolist()],zStd=[round(x,3) for x in zStd.tolist()],
                rest=restMeta,dataFile=dn,
                conditions=[dict(key=c,label=disp[c][0],cue=disp[c][1]) for c in cond_keys])

# ---------- T5 (handwriting) ----------
def load_t5():
    p=need(os.path.join(RAW,"handwritingBCIData/Datasets/t5.2019.05.08/singleLetters.mat"),
           "T5 handwriting session (Willett 2021)")
    m=sio.loadmat(p, squeeze_me=True, struct_as_record=False)
    TS=np.asarray(m['neuralActivityTimeSeries']); goOn=np.asarray(m['goPeriodOnsetTimeBin']).astype(int)
    cueOn=np.asarray(m['delayPeriodOnsetTimeBin']).astype(int); tokens=[str(x) for x in np.asarray(m['characterCues']).ravel()]
    blk=np.asarray(m['blockNumsTimeSeries']).ravel()
    SYM={'apostrophe':("'","'"),'comma':(",",","),'greaterThan':(">",">"),'questionMark':("?","?"),'tilde':("~","~"),'doNothing':("DO_NOTHING","—")}
    keys=set(tokens); letters=sorted([k for k in keys if len(k)==1 and k.isalpha()])
    syms=[k for k in ['apostrophe','comma','greaterThan','questionMark','tilde'] if k in keys]
    cond_keys=letters+syms+(['doNothing'] if 'doNothing' in keys else [])
    disp={c:(SYM[c] if c in SYM else (c,c.upper())) for c in cond_keys}
    geo=np.asarray(m['arrayGeometryMap']).astype(int).ravel().tolist()
    arrays=[dict(id='A1',label='Array 1',sub='96 ch · 6v',offset=0),dict(id='A2',label='Array 2',sub='96 ch · 6v',offset=96)]
    return build_user('t5','T5 · handwriting','Willett 2021 · 2019.05.08',TS,goOn,cueOn,tokens,blk,
                      cond_keys,disp,geo,10,10,arrays,192,10,-3000,2000,2.0)

# ---------- Kunz verbal behaviors (T12 / T15 / T16 / T17) ----------
KUNZ_DIR = "kunz/isolatedVerbalBehaviors/isolatedVerbalBehaviors"
KUNZ_SESSION = {'t12':'2023.08.15', 't15':'2024.04.07', 't16':'2024.03.04', 't17':'2024.12.09'}
PANEL = 64          # channels per displayed array panel (8x8 grid)

def kunz_arrays(m, nCh):
    """chanSets/chanSetNames -> the app's equal-sized array panels.

    Participants differ: T12 has two 64-ch sets, T15 four, while T16 ('6d') and T17
    ('55b') each carry a 128-ch set. The app gives every array one shared 8x8 grid and
    derives channels-per-array as nCh/len(arrays), so a 128-ch set is split into two
    64-ch panels ('6d-1', '6d-2'). The sets are contiguous 1-based ranges in file
    order, which is what lets a panel be addressed by a single channel offset.
    """
    names=[str(x) for x in np.asarray(m['chanSetNames']).ravel()]
    sets=np.asarray(m['chanSets'],dtype=object).ravel()
    arrays=[]
    for name,s in zip(names,sets):
        idx=np.asarray(s).ravel().astype(int)
        lo,hi=int(idx.min()),int(idx.max())
        if not np.array_equal(np.sort(idx),np.arange(lo,hi+1)):
            raise SystemExit(f"chanSet '{name}' is not a contiguous range; the offset model needs one")
        n=hi-lo+1
        if n%PANEL: raise SystemExit(f"chanSet '{name}' has {n} channels, not a multiple of {PANEL}")
        parts=n//PANEL
        for k in range(parts):
            lbl=name if parts==1 else f"{name}-{k+1}"
            arrays.append(dict(id='A%d'%(len(arrays)+1), label=lbl,
                               sub=f"{PANEL} ch · {name}", offset=lo-1+k*PANEL))
    got=sum(PANEL for _ in arrays)
    if got!=nCh: raise SystemExit(f"arrays cover {got} channels but binnedTX has {nCh}")
    return arrays

def load_kunz(uid, behavior='attempted'):
    p=need(os.path.join(RAW,KUNZ_DIR,"%s.%s_%s_raw.mat"%(uid,KUNZ_SESSION[uid],behavior)),
           "%s verbal-behaviors session (Kunz)"%uid.upper())
    m=sio.loadmat(p, squeeze_me=True, struct_as_record=False)
    TS=np.asarray(m['binnedTX']); nCh=int(TS.shape[1])
    binMs=int(np.asarray(m['binSize']).ravel()[0])       # 20 for T12, 10 for the rest
    goOn=np.asarray(m['goTrialEpochs'])[:,0].astype(int)
    cueOn=np.asarray(m['delayTrialEpochs'])[:,0].astype(int)
    cueList=[str(x) for x in np.asarray(m['cueList']).ravel()]
    tc=np.asarray(m['trialCues']).ravel().astype(int)
    tokens=[cueList[c-1] for c in tc]                    # trialCues are 1-indexed into cueList
    blk=np.asarray(m['blockNum']).ravel()
    words=[w for w in cueList if w!='DO_NOTHING']
    cond_keys=words+['DO_NOTHING']
    disp={w:(w,w.upper()) for w in words}; disp['DO_NOTHING']=('DO_NOTHING','—')
    geo=list(range(1,PANEL+1))                           # 8x8 row-major (no wiring map available)
    # sigma is set in bins; 20/binMs keeps the smoothing at 20 ms for every participant
    return build_user(uid,'%s · speech'%uid.upper(),'Kunz 2025 · %s · %s'%(KUNZ_SESSION[uid],behavior),
                      TS,goOn,cueOn,tokens,blk,cond_keys,disp,geo,8,8,
                      kunz_arrays(m,nCh),nCh,binMs,-3000,4000,20.0/binMs)

KUNZ_USERS = ['t12', 't15', 't16', 't17']

def main():
    print("building users...")
    users=[load_t5()]+[load_kunz(u) for u in KUNZ_USERS]
    manifest=dict(users=users, defaultUser='t5')
    json.dump(manifest, open(os.path.join(OUT,'manifest.json'),'w'))
    print(f"\nmanifest.json {os.path.getsize(os.path.join(OUT,'manifest.json'))/1e3:.1f}KB · users: "+", ".join(u['id'] for u in users))

if __name__=='__main__': main()
