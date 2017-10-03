#!/usr/bin/env python
import os, sys
import ROOT
ROOT.PyConfig.IgnoreCommandLineOptions = True
from importlib import import_module
from glob import glob
import re, pickle, math
from CMGTools.MonoXAnalysis.postprocessing.framework.postprocessor import PostProcessor

if __name__ == "__main__":
    from optparse import OptionParser
    parser = OptionParser(usage="%prog [options] inputDir outputDir")
    parser.add_option("-J", "--json",  dest="json", type="string", default=None, help="Select events using this JSON file")
    parser.add_option("-C", "--cut",  dest="cut", type="string", default=None, help="Cut string")
    parser.add_option("-b", "--branch-selection",  dest="branchsel", type="string", default=None, help="Branch selection")
    parser.add_option("--friend",  dest="friend", action="store_true", default=False, help="Produce friend trees in output (current default is to produce full trees)")
    parser.add_option("--full",  dest="friend", action="store_false",  default=False, help="Produce full trees in output (this is the current default)")
    parser.add_option("--noout",  dest="noOut", action="store_true",  default=False, help="Do not produce output, just run modules")
    parser.add_option("--justcount",   dest="justcount", default=False, action="store_true",  help="Just report the number of selected events") 
    parser.add_option("-I", "--import", dest="imports",  type="string", default=[], action="append", nargs=2, help="Import modules (python package, comma-separated list of ");
    parser.add_option("-z", "--compression",  dest="compression", type="string", default=("LZMA:9"), help="Compression: none, or (algo):(level) ")
    parser.add_option("-d", "--dataset", dest="datasets",  type="string", default=[], action="append", help="Process only this dataset (or dataset if specified multiple times)");
    parser.add_option("-c", "--chunk",   dest="chunks",    type="int",    default=[], action="append", help="Process only these chunks (works only if a single dataset is selected with -d)");
    parser.add_option("-N", "--events",  dest="chunkSize", type="int",    default=500000, help="Default chunk size when splitting trees");
    parser.add_option("-j", "--jobs",    dest="jobs",      type="int",    default=1, help="Use N threads");
    parser.add_option("-q", "--queue",   dest="queue",     type="string", default=None, help="Run jobs on lxbatch instead of locally");
    parser.add_option("-t", "--tree",    dest="tree",      default='treeProducerWMass', help="Pattern for tree name");

    (options, args) = parser.parse_args()

    if options.friend:
        if options.cut or options.json: raise RuntimeError("Can't apply JSON or cut selection when producing friends")

    if len(args) != 2 or not os.path.isdir(args[0]):
        parser.print_help()
        sys.exit(1)
    if len(options.chunks) != 0 and len(options.datasets) != 1:
        print "must specify a single dataset with -d if using -c to select chunks"
        sys.exit(1)

    treedir = args[0]; outdir=args[1]; args = args[2:]

    jobs = []
    for D in glob(treedir+"/*"):
        treename = "tree"
        fname    = "%s/%s/tree.root" % (D,options.tree)
        pckfile  = "%s/skimAnalyzerCount/SkimReport.pck" % (D)
        if (not os.path.exists(fname)) and os.path.exists("%s/%s/tree.root" % (D,options.tree)):
            treename = "tree"
            fname    = "%s/%s/tree.root" % (D,options.tree)
     
        if (not os.path.exists(fname)) and (os.path.exists("%s/%s/tree.root.url" % (D,options.tree)) ):
            treename = "tree"
            fname    = "%s/%s/tree.root" % (D,options.tree)
            fname    = open(fname+".url","r").readline().strip()
     
        if os.path.exists(fname) or (os.path.exists("%s/%s/tree.root.url" % (D,options.tree))):
            short = os.path.basename(D)
            if options.datasets != []:
                if short not in options.datasets: continue
            data = any(x in short for x in "DoubleMu DoubleEG MuEG MuonEG SingleMu SingleEl".split())
            pckobj  = pickle.load(open(pckfile,'r'))
            counters = dict(pckobj)
            if ('Sum Weights' in counters):
                sample_nevt = counters['Sum Weights']
            else:
                sample_nevt = counters['All Events']
            f = ROOT.TFile.Open(fname);
            t = f.Get(treename)
            entries = t.GetEntries()
            f.Close()
            chunk = options.chunkSize
            if entries < chunk:
                print "  ",os.path.basename(D),("  DATA" if data else "  MC")," single chunk"
                jobs.append((short,fname,sample_nevt,"_Friend_%s"%short,data,xrange(entries),-1))
            else:
                nchunk = int(math.ceil(entries/float(chunk)))
                print "  ",os.path.basename(D),("  DATA" if data else "  MC")," %d chunks" % nchunk
                for i in xrange(nchunk):
                    if options.chunks != []:
                        if i not in options.chunks: continue
                    r = xrange(int(i*chunk),min(int((i+1)*chunk),entries))
                    jobs.append((short,fname,sample_nevt,"_Friend_%s.chunk%d" % (short,i),data,r,i))
    print "\n"
    print "I have %d taks to process" % len(jobs)

    if options.queue:
        import os, sys
        basecmd = "bsub -q {queue} {dir}/lxbatch_runner.sh {dir} {cmssw} python {self} -N {chunkSize} -t {tree} {data} {output}".format(
                    queue = options.queue, dir = os.getcwd(), cmssw = os.environ['CMSSW_BASE'], 
                    self=sys.argv[0], chunkSize=options.chunkSize, tree=options.tree, data=treedir, output=outdir
                )
        for (name,fin,sample_nevt,fout,data,range,chunk) in jobs:
            if chunk != -1:
                print "{base} -d {data} -c {chunk}".format(base=basecmd, data=name, chunk=chunk)
            else:
                print "{base} -d {data}".format(base=basecmd, data=name, chunk=chunk)
            
        exit()

    maintimer = ROOT.TStopwatch()
    def _runIt(myargs):
        (name,fin,sample_nevt,fout,data,range,chunk) = myargs
     
        fetchedfile = None
        if 'LSB_JOBID' in os.environ or 'LSF_JOBID' in os.environ:
            if fin.startswith("root://"):
                try:
                    tmpdir = os.environ['TMPDIR'] if 'TMPDIR' in os.environ else "/tmp"
                    tmpfile =  "%s/%s" % (tmpdir, os.path.basename(fin))
                    print "xrdcp %s %s" % (fin, tmpfile)
                    os.system("xrdcp %s %s" % (fin, tmpfile))
                    if os.path.exists(tmpfile):
                        fin = tmpfile 
                        fetchedfile = fin
                        print "success :-)"
                except:
                    pass
            #fb = ROOT.TFile.Open(fin)
        elif "root://" in fin:        
            ROOT.gEnv.SetValue("TFile.AsyncReading", 1);
            ROOT.gEnv.SetValue("XNet.Debug", 0); # suppress output about opening connections
            ROOT.gEnv.SetValue("XrdClientDebug.kUSERDEBUG", 0); # suppress output about opening connections
            #fb   = ROOT.TXNetFile(fin+"?readaheadsz=65535&DebugLevel=0")
            os.environ["XRD_DEBUGLEVEL"]="0"
            os.environ["XRD_DebugLevel"]="0"
            os.environ["DEBUGLEVEL"]="0"
            os.environ["DebugLevel"]="0"
        else:
            #fb = ROOT.TFile.Open(fin)
            #print fb
            pass
     
        modules = []
        for mod, names in options.imports: 
            import_module(mod)
            obj = sys.modules[mod]
            selnames = names.split(",")
            for name in dir(obj):
                if name[0] == "_": continue
                if name in selnames:
                    print "Loading %s from %s " % (name, mod)
                    modules.append(getattr(obj,name)())
        if options.noOut:
            if len(modules) == 0: 
                raise RuntimeError("Running with --noout and no modules does nothing!")
        ppargs=[fin]+args
        p=PostProcessor(outdir,ppargs,options.cut,options.branchsel,modules,options.compression,options.friend,fout,options.json,options.noOut,options.justcount,range)
        p.run()

    if options.jobs > 0:
        from multiprocessing import Pool
        pool = Pool(options.jobs)
        pool.map(_runIt, jobs) if options.jobs > 0 else [_runIt(j) for j in jobs]
    else:
        ret = dict(map(_runIt, jobs))
