"""Preregistered paired analysis; synthetic self-tests only in stage 1."""
import math
import numpy as np

def paired_signflip(differences,draws=100000,seed=20261116):
    d=np.asarray(differences,dtype=float)
    if d.ndim!=1 or not len(d) or not np.isfinite(d).all():raise ValueError('invalid_differences')
    observed=abs(d.mean());rng=np.random.default_rng(seed);count=0
    for start in range(0,draws,1000):
        n=min(1000,draws-start);signs=rng.choice([-1,1],size=(n,len(d)))
        count+=int(np.count_nonzero(abs((signs*d).mean(axis=1))>=observed-1e-12))
    return (count+1)/(draws+1)

def holm(pvalues):
    ranked=sorted(enumerate(pvalues),key=lambda x:x[1]);out=[None]*len(ranked);prev=0
    for rank,(idx,p) in enumerate(ranked):
        if not 0<=p<=1:raise ValueError('invalid_p')
        prev=max(prev,min(1.,(len(ranked)-rank)*p));out[idx]=prev
    return out

def exact_mcnemar(b,c):
    if type(b) is not int or type(c) is not int or min(b,c)<0:raise ValueError('invalid_counts')
    n=b+c
    return min(1.,2*sum(math.comb(n,k) for k in range(min(b,c)+1))/2**n) if n else 1.

def stratified_paired_interval(differences,repositories,draws=20000,seed=20261116):
    d=np.asarray(differences,dtype=float)
    if len(d)!=len(repositories) or not len(d) or not np.isfinite(d).all():raise ValueError('invalid_inputs')
    groups=[[i for i,x in enumerate(repositories) if x==repo] for repo in sorted(set(repositories))]
    rng=np.random.default_rng(seed);means=[]
    for _ in range(draws):
        idx=np.concatenate([rng.choice(g,len(g),replace=True) for g in groups]);means.append(float(d[idx].mean()))
    return np.quantile(means,[.025,.975]).tolist()
