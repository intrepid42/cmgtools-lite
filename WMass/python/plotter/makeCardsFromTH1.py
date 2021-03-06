#!/usr/bin/env python                                                                                                     
 
from shutil import copyfile
import re, sys, os, os.path, subprocess, json, ROOT
import numpy as np

from w_helicity_13TeV.make_diff_xsec_cards import getXYBinsFromGlobalBin
from w_helicity_13TeV.make_diff_xsec_cards import getArrayParsingString
from w_helicity_13TeV.make_diff_xsec_cards import getDiffXsecBinning
from w_helicity_13TeV.make_diff_xsec_cards import getArrayBinNumberFromValue
from w_helicity_13TeV.make_diff_xsec_cards import templateBinning
from w_helicity_13TeV.make_diff_xsec_cards import get_ieta_ipt_from_process_name

from w_helicity_13TeV.mergeCardComponentsDiffXsec import getXsecs_etaPt

# originally developed to make cards for diff xsec in lepton pt and |eta|
# first run to make cards and xsec files, then run again using same options and adding options --comb-charge [ --no-text2hdf5 [ --freezePOIs ] ]
# option sparse is used by default, which is fine or double-differential cross section. In case this script is adapted for helicity, that should not be used

# example (root file in input is just a dummy)
## python makeCardsFromTH1.py -i cards/diffXsec_mu_2018_11_24_group10_onlyBkg/ -f mu -c plus -s w-helicity-13TeV/wmass_mu/systsEnv.txt

## python makeCardsFromTH1.py -i cards/diffXsec_el_2018_11_25_group10_onlyBkg_recoEta2p5/ -f el -c plus -s w-helicity-13TeV/wmass_e/systsEnv.txt --sig-out-outAcc --eta-range-outAcc 1.45 2.55 

def isExcludedNuisance(excludeNuisances=[], name=""):
    if len(excludeNuisances) and any(re.match(x,name) for x in excludeNuisances): 
        print ">>>>> Excluding nuisance: ", name
        return True
    else:
        return False


def combCharges(options):
    suffix = 'card' if options.freezePOIs else 'card_withXsecMask'
    datacards=[]; channels=[]
    for charge in ['plus','minus']:
        datacards.append(os.path.abspath(options.outdir)+"/"+options.bin+'_{ch}_card.txt'.format(ch=charge))
        channels.append('{bin}_{ch}'.format(bin=options.bin,ch=charge))
        maskedChannels = ['InAcc']
        if len(options.eta_range_outAcc) or options.sig_out_outAcc:
            maskedChannels.append('OutAcc')
        if not options.freezePOIs:
            for mc in maskedChannels:
                datacards.append(os.path.abspath(options.outdir)+"/"+options.bin+'_{ch}_xsec_{maskchan}_card.txt'.format(ch=charge,maskchan=mc))
                channels.append('{bin}_{ch}_xsec_{maskchan}'.format(bin=options.bin,ch=charge,maskchan=mc))

    print "="*20
    print "Looking for these cards"
    print "-"*20
    for d in datacards:
        print d
    print "="*20

    if sum([os.path.exists(card) for card in datacards])==len(datacards):
        print "Cards for W+ and W- done. Combining them now..."
        combinedCard = os.path.abspath(options.outdir)+"/"+options.bin+'_'+suffix+'.txt'
        ccCmd = 'combineCards.py --noDirPrefix '+' '.join(['{channel}={dcfile}'.format(channel=channels[i],dcfile=datacards[i]) for i,c in enumerate(channels)])+' > '+combinedCard
        ## here running the combine cards command first 
        print ccCmd
        os.system(ccCmd)
        ## here making the TF meta file
        if options.freezePOIs:
            # doesn't make sense to have the xsec masked channel if you freeze the rates (POIs) -- and doesn't work either
            txt2hdf5Cmd = 'text2hdf5.py --sparse {cf}'.format(cf=combinedCard)
        else:
            maskchan = [' --maskedChan {bin}_{charge}_xsec_{maskchan}'.format(bin=options.bin,charge=ch,maskchan=mc) for ch in ['plus','minus'] for mc in maskedChannels]
            txt2hdf5Cmd = 'text2hdf5.py --sparse {maskch} --X-allow-no-background {cf}'.format(maskch=' '.join(maskchan),cf=combinedCard)
        if not options.doSystematics:
            txt2hdf5Cmd = txt2hdf5Cmd.replace("text2hdf5.py ","text2hdf5.py -S 0 ")
        if len(options.postfix):
            txt2hdf5Cmd = txt2hdf5Cmd + " --postfix " + options.postfix
        print ""
        print "The following command makes the .hdf5 file used by combine"
        print txt2hdf5Cmd
        print '--- will run text2hdf5 for the combined charges ---------------------'
        if not options.skip_text2hdf5: os.system(txt2hdf5Cmd)
        ## print out the command to run in combine
        metafilename = combinedCard.replace('.txt','_sparse.hdf5')
        if len(options.postfix):
            metafilename = metafilename.replace('_sparse.hdf5','_sparse_%s.hdf5' % options.postfix)

        bbboptions = " --binByBinStat --correlateXsecStat "
        combineCmd = 'combinetf.py -t -1 {bbb} {metafile}'.format(metafile=metafilename, bbb="" if options.noBBB else bbboptions)
        if options.freezePOIs:
            combineCmd += " --POIMode none"
        else:
            combineCmd += " --doImpacts  "
        fitdir_data = "{od}/fit/data/".format(od=os.path.abspath(options.outdir))
        fitdir_Asimov = "{od}/fit/hessian/".format(od=os.path.abspath(options.outdir))
        if not os.path.exists(fitdir_data):
            print "Creating folder", fitdir_data
            os.system("mkdir -p " + fitdir_data)
        if not os.path.exists(fitdir_Asimov):
            print "Creating folder", fitdir_Asimov
            os.system("mkdir -p " + fitdir_Asimov)
        print ""
        # add --saveHists --computeHistErrors 
        print "Use the following command to run combine (add --seed <seed> to specify the seed, if needed). See other options in combinetf.py"
        combineCmd_data = combineCmd.replace("-t -1 ","-t 0 ")
        combineCmd_data = combineCmd_data + " --postfix Data{pf}_bbb{b} --outputDir {od} --saveHists --computeHistErrors ".format(pf="" if not len(options.postfix) else ("_"+options.postfix), od=fitdir_data, b="0" if options.noBBB else "1_cxs1")
        combineCmd_Asimov = combineCmd + " --postfix Asimov{pf}_bbb{b} --outputDir {od}  --saveHists --computeHistErrors  ".format(pf="" if not len(options.postfix) else ("_"+options.postfix), od=fitdir_Asimov, b="0" if options.noBBB else "1_cxs1")
        print combineCmd_data
        if not options.skip_combinetf:
            os.system(combineCmd_data)
        print ""
        print combineCmd_Asimov            
        if not options.skip_combinetf:
            os.system(combineCmd_Asimov)
            

    else:
        print "It looks like at least one of the datacards for a single charge is missing. I cannot make the combination."



from optparse import OptionParser
parser = OptionParser(usage="%prog [options]")
parser.add_option("-i", "--indir",     dest="indir", type="string", default="./", help="Input folder with shape file");
parser.add_option("-o", "--outdir",    dest="outdir", type="string", default="SAME", help="Output folder (if SAME, use the same as input)");
parser.add_option("-n", "--name",      dest="name",   type="string", default="", help="Name for output datacard (if not given, name is W<flavou>_<charge>_card.txt ).");
parser.add_option("-f", "--flavour",   dest="flavour", type="string", default='', help="Channel: either 'el' or 'mu'");
parser.add_option("-g", "--group",     dest="group", type="int", default='0', help="In case signal bins for diff.xsec were grouped, the number of grouped bins appears in the name of the process as '<name>_group<n>'. Just for backward compatibility");
parser.add_option("-c", "--charge",    dest="charge", type="string", default='', help="Charge: either 'plus' or 'minus'");
parser.add_option("-b", "--bin",       dest="bin", default="", type="string", help="name of the bin. If not given, it becomes 'W<flavour>'")
parser.add_option("-s", "--syst-file", dest="systfile", default="", type="string", help="File defining the systematics (only the constant ones are used)")
parser.add_option(      '--binfile'  , dest='binfile', default='binningPtEta.txt', type='string', help='eta-pt binning for templates, by default it is expected to be in input folder')
parser.add_option(      '--xsecMaskedYields', dest='xsecMaskedYields', default=False, action='store_true', help='use the xsec in the masked channel, not the expected yield')
parser.add_option(      '--unbinned-QCDscale-W', dest='unbinnedQCDscaleW', default=False, action='store_true', help='Assign muR, muF and muRmuF to W (those in bins of W-pt will be used for W in any case)')
parser.add_option(      '--unbinned-QCDscale-Z', dest='unbinnedQCDscaleZ', default=False, action='store_true', help='Assign muR, muF and muRmuF to Z')
parser.add_option(      '--no-EffStat-Z', dest='noEffStatZ', default=False, action='store_true', help='If True, abort EffStat nuisances on Z')
parser.add_option(       '--wXsecLnN'   , dest='wLnN'        , default=0.0, type='float', help='Log-normal constraint to be added to all the fixed W processes or considered as background (might be 0.038)')
parser.add_option(       '--sig-out-bkg', dest='sig_out_bkg' , default=False, action='store_true', help='Will treat signal bins corresponding to outliers as background processes')
parser.add_option(       '--eta-range-bkg', dest='eta_range_bkg', action="append", type="float", nargs=2, default=[], help='Will treat signal templates with gen level eta in this range as background in the datacard. Takes two float as arguments (increasing order) and can specify multiple times. They should match bin edges and a bin is not considered as background if at least one edge is outside this range')
parser.add_option(       '--pt-range-bkg', dest='pt_range_bkg', action="append", type="float", nargs=2, default=[], help='Will treat signal templates with gen level pt in this range as background in the datacard. Takes two float as arguments (increasing order) and can specify multiple times. They should match bin edges and a bin is not considered as background if at least one edge is outside this range')
parser.add_option(       '--sig-out-outAcc', dest='sig_out_outAcc' , default=False, action='store_true', help='Will treat signal bins corresponding to outliers as an out of acceptance channel, it will be fitted as any signal bin, but form a separate channel')
parser.add_option(       '--eta-range-outAcc', dest='eta_range_outAcc', action="append", type="float", nargs=2, default=[], help='Will treat signal templates with gen level eta in this range as a separate out-of-acceptance channel in the datacard. Takes two float as arguments (increasing order) and can specify multiple times. They should match bin edges and a bin is not considered as out-of-acceptance if at least one edge is outside this range. For the outliers template, use option --sig-out-outAcc')
parser.add_option(       '--comb-charge'          , dest='combineCharges' , default=False, action='store_true', help='Combine W+ and W-, if single cards are done. It ignores some options, since it is executed immediately and quit right afterwards')
parser.add_option('--fp','--freezePOIs'  , dest='freezePOIs'   , default=False, action='store_true', help='run tensorflow with --freezePOIs (for the pdf only fit)')
parser.add_option(       '--no-text2hdf5'  , dest='skip_text2hdf5', default=False, action='store_true', help='when combining charges, skip running text2hdf5.py at the end')
parser.add_option(       '--no-combinetf'  , dest='skip_combinetf', default=False, action='store_true', help='when combining charges, skip running combinetf.py at the end')
parser.add_option(       '--no-bbb'  , dest='noBBB', default=False, action='store_true', help='Do not use bin-by-bin uncertainties')
parser.add_option("-S",  "--doSystematics", type=int, default=1, help="enable systematics when running text2hdf5.py (-S 0 to disable them)")
parser.add_option(       "--exclude-nuisances", dest="excludeNuisances", default="", type="string", help="Pass comma-separated list of regular expressions to exclude some systematics")
parser.add_option("-p", "--postfix",    dest="postfix", type="string", default="", help="Postfix for .hdf5 file created with text2hdf5.py when combining charges");
parser.add_option(       '--preFSRxsec', dest='preFSRxsec' , default=False, action='store_true', help='Use gen cross section made with preFSR lepton. Alternative is dressed, which might be  relevant for some things like QCD scales in Wpt bins')
(options, args) = parser.parse_args()

print ""
if not options.indir:
    print "Warning: you must specify an input folder containing the shape files with option -i <dir>"
    quit()
if options.flavour not in ["el", "mu"]:
    print "Warning: you must specify a lepton flavour with option -f el|mu"
    quit()
if not options.combineCharges:
    if options.charge not in ["plus", "minus"]:
        print "Warning: you must specify a charge with option -c plus|minus"
        quit()

if options.sig_out_bkg and options.sig_out_outAcc:
    print "Warning: outliers cannot be considered as a background and an out-of-acceptance template. Select either --sig-out-outAcc or --sig-out-bkg"
    quit()

if not options.indir.endswith('/'): options.indir += "/"    
# manage output folder
outdir = options.outdir
if outdir == "SAME": outdir = options.indir
if not outdir.endswith('/'): outdir += "/"
if outdir != "./":
    if not os.path.exists(outdir):
        print "Creating folder", outdir
        os.system("mkdir -p " + outdir)

charge = options.charge
flavour = options.flavour
binname = options.bin if len(options.bin) else "W%s" % flavour
signalMatch = "W%s" % charge

if options.combineCharges:
    cmssw = os.environ['CMSSW_VERSION']
    if cmssw != "":
        if cmssw == "CMSSW_8_0_25":
            print "ERROR: you must be in CMSSW_10_3_0_pre4 or newer to run this command and use combine with tensorflow. Exit"
            quit()
    else:
        print "ERROR: need to set cmssw environment. Run cmsenv from CMSSW_10_3_0_pre4 or newer to run this command and use combine with tensorflow. Exit"
        quit()

    options.bin = binname
    options.outdir = outdir # to pass to combCharges()
    combCharges(options)
    print ""
    print "I combined the datacards for both charges."
    quit()

etaPtBinningFile = options.indir + options.binfile
# get eta-pt binning for both reco and gen
etaPtBinningVec = getDiffXsecBinning(etaPtBinningFile, "reco")
recoBins = templateBinning(etaPtBinningVec[0],etaPtBinningVec[1])
etaPtGenBinningVec = getDiffXsecBinning(etaPtBinningFile, "gen")
genBins  = templateBinning(etaPtGenBinningVec[0],etaPtGenBinningVec[1])
#
#recoBins.printBinAll()
#genBins.printBinAll()

binning = [genBins.Neta, genBins.etaBins, genBins.Npt, genBins.ptBins]

allSystForGroups = [] # filled with all systs not excluded by excludeNuisances
excludeNuisances = []
if len(options.excludeNuisances):
    excludeNuisances = options.excludeNuisances.split(",")

# consider some signal bins as background
etaBinIsBackground = []  # will store a bool to assess whether the given ieta index is considered as background
for bin in range(genBins.Neta):
    etaBinIsBackground.append(False)
etaRangesBkg = options.eta_range_bkg
if len(etaRangesBkg):
    hasEtaRangeBkg = True
    print "Signal bins with gen eta in the following ranges will be considered as background processes"
    print options.eta_range_bkg            
    for index in range(genBins.Neta):
        for pair in etaRangesBkg:
        #print pair
            if genBins.etaBins[index] >= pair[0] and genBins.etaBins[index+1] <= pair[1]:
                etaBinIsBackground[index] = True
else:
    hasEtaRangeBkg = False

# consider some signal bins as background
ptBinIsBackground = []  # will store a bool to assess whether the given ipt index is considered as background
for bin in range(genBins.Npt):
    ptBinIsBackground.append(False)
ptRangesBkg = options.pt_range_bkg
if len(ptRangesBkg):
    hasPtRangeBkg = True
    print "Signal bins with gen pt in the following ranges will be considered as background processes"
    print options.pt_range_bkg            
    for index in range(genBins.Npt):
        for pair in ptRangesBkg:
        #print pair
            if genBins.ptBins[index] >= pair[0] and genBins.ptBins[index+1] <= pair[1]:
                ptBinIsBackground[index] = True
else:
    hasPtRangeBkg = False

### outAcc
etaBinIsOutAcc = []  # will store a bool to assess whether the given ieta index is considered as background
for bin in range(genBins.Neta):
    etaBinIsOutAcc.append(False)
etaRangesOutAcc = options.eta_range_outAcc
if len(etaRangesOutAcc):
    hasEtaRangeOutAcc = True
    print "Signal bins with gen eta in the following ranges will be considered as out-of-acceptance processes, and will go in a separate masked channel"
    print options.eta_range_outAcc            
    for index in range(genBins.Neta):
        for pair in etaRangesOutAcc:
        #print pair
            if genBins.etaBins[index] >= pair[0] and genBins.etaBins[index+1] <= pair[1]:
                etaBinIsOutAcc[index] = True
else:
    hasEtaRangeOutAcc = False

# signal processes are like
# x_Wplus_mu_ieta_22_ipt_3_Wplus_mu_group_9_muRmuFUp
# x_Wplus_mu_outliers_Wplus_mu_outliers_group_46_pdf58Down
# group might not be in the name when signal bins are made with the loop

bkgprocesses = ["Z", "TauDecaysW", "Top", "DiBosons", "data_fakes"]
if flavour == "el": bkgprocesses.append("Flips")

signalprocesses = []
igroup = 0
for ieta in range(genBins.Neta):
    for ipt in range(genBins.Npt):
        if options.group:
            igroup = int(int(ieta + ipt * genBins.Neta)/options.group)
            sigName = "W{ch}_{fl}_ieta_{ieta}_ipt_{ipt}_W{ch}_{fl}_group_{gr}".format(ch=charge, fl=flavour, ieta=str(ieta), ipt=str(ipt), gr=str(igroup))
        else:
            sigName = "W{ch}_{fl}_ieta_{ieta}_ipt_{ipt}_W{ch}_{fl}".format(ch=charge, fl=flavour, ieta=str(ieta), ipt=str(ipt))            
        signalprocesses.append(sigName)
# add last bin with outliers (outlirs might be written in name once or twice, please check
sigOutName = "W{ch}_{fl}_outliers_W{ch}_{fl}".format(ch=charge, fl=flavour)
if options.group:
    sigOutName += "_group_{gr}".format(gr=str(igroup+1))
signalprocesses.append(sigOutName)

allprocesses = bkgprocesses + signalprocesses
procNum = {}
isig = 0
ibkg = 1
procIsSignalBkg = {}

for p in allprocesses:
    procIsSignalBkg[p] = False
    if signalMatch in p: 
        if "outliers" in p and options.sig_out_bkg:            
            procNum[p] = ibkg
            ibkg += 1
            procIsSignalBkg[p] = True
        else:
            ieta,ipt = get_ieta_ipt_from_process_name(p)
            if ((hasPtRangeBkg and ptBinIsBackground[ipt]) or (hasEtaRangeBkg and etaBinIsBackground[ieta])):
                procNum[p] = ibkg
                ibkg += 1    
                procIsSignalBkg[p] = True
            else:
                procNum[p] = isig
                isig -= 1
    else:
        procNum[p] = ibkg
        ibkg += 1

# get yields in data
yieldsData = 0
shapefile = "{i}W{fl}_{ch}_shapes.root".format(i=options.indir,fl=flavour,ch=charge)
shapefile = os.path.abspath(shapefile)
tf = ROOT.TFile.Open(shapefile,"READ")
if not tf or not tf.IsOpen():
    raise RuntimeError('Unable to open file {fn}'.format(fn=shapefile))
else:
    histData = tf.Get("x_data_obs")
    if not histData:
        raise RuntimeError('Unable to retrieve histogram named x_data_obs')    
    else:           
        yieldsData = histData.Integral()
tf.Close()


cardname = ""
if cardname == "":
    cardname = "{od}W{fl}_{ch}_card.txt".format(od=outdir, fl=flavour, ch=charge)
else:
    cardname = outdir + options.name

card = open(cardname,'w')

card.write("imax 1\n")
card.write("jmax *\n")
card.write("kmax *\n")
card.write("##-----------------------------\n")
card.write("shapes * * {sh} x_$PROCESS x_$PROCESS_$SYSTEMATIC\n".format(sh=shapefile))
card.write("##-----------------------------\n")
card.write("bin %s\n" % binname)
card.write("observation %d\n" % yieldsData)
card.write("##-----------------------------\n")

maxproclen = 0
for proc in allprocesses:
    if len(proc) > maxproclen:
        maxproclen = len(proc)
klen = min(20,maxproclen + 3)
kpatt = " %%%ds "  % klen
card.write('bin                 %s \n' % ' '.join([kpatt % binname for p in allprocesses]))
card.write('process             %s \n' % ' '.join([kpatt % p       for p in allprocesses]))
card.write('process             %s \n' % ' '.join([kpatt % str(procNum[p])  for p in allprocesses]))
card.write('rate                %s \n' % ' '.join([kpatt % "-1"    for p in allprocesses]))
card.write("---------------------------------------------------------------------------------------\n")

# now other systematics
#First those that are constant, from w-helicity-13TeV/wmass_e/systsEnv.txt
#print "Now loading systematics"
truebinname = binname  # this is just a dummy variable, it is used below to match binmap from the sysfile: as far as I know is always binmap='.*' (all bins)
if options.systfile != "":
    #sysfile = os.environ['CMSSW_BASE']+'/src/CMGTools/WMass/python/plotter/'+options.systfile
    sysfile = options.systfile
    systs = {}
    for line in open(sysfile, 'r'):
        if re.match("\s*#.*", line): continue
        line = re.sub("#.*","",line).strip()
        if len(line) == 0: continue
        field = [f.strip() for f in line.split(':')]
        #print field
        if len(field) < 4:
            raise RuntimeError, "Malformed line %s in file %s"%(line.strip(),sysfile)
        elif len(field) == 4 or field[4] == "lnN":
            (name, procmap, binmap, amount) = field[:4]
            if re.match(binmap+"$",truebinname) == None: continue
            if name not in systs: systs[name] = []
            systs[name].append((re.compile(procmap+"$"),amount))
    #print "Loaded %d systematics" % len(systs)

    for name in systs.keys():
        effmap = {}
        for p in allprocesses:
            effect = "-"
            for (procmap,amount) in systs[name]:
                if re.match(procmap, p): effect = amount
            # if effect not in ["-","0","1"]:
            #     if "/" in effect:
            #         e1, e2 = effect.split("/")
            #         effect = "%.3f/%.3f" % (mca._projection.scaleSyst(name, float(e1)), mca._projection.scaleSyst(name, float(e2)))
            #     else:
            #         effect = str(mca._projection.scaleSyst(name, float(effect)))
            effmap[p] = effect
        systs[name] = effmap
    for name,effmap in systs.iteritems():
        if isExcludedNuisance(excludeNuisances, name): continue
        allSystForGroups.append(name)
        card.write(('%-16s lnN' % name) + " ".join([kpatt % effmap[p]   for p in allprocesses]) +"\n")


# norm unc on signal processes treated as background
# if some signal bins are treated as background, assign 3.8% norm uncertainty
if options.wLnN > 0.0 and (hasPtRangeBkg or hasEtaRangeBkg or options.sig_out_bkg):
    Wxsec   = "{0:.3f}".format(1.0 + options.wLnN)    #"1.038"  # 3.8%
    if not isExcludedNuisance(excludeNuisances, "CMS_Wbkg"): 
        allSystForGroups.append("CMS_Wbkg")
        card.write(('%-16s lnN' % "CMS_Wbkg") + ' '.join([kpatt % (Wxsec if procIsSignalBkg[p] else "-") for p in allprocesses]) + "\n")

###########
####### Nuisances for fakes

# independent eta normalizations variations for fakes, by 5%. 
# Get the actual number counting the histograms in case it changes or is not present
ffile = options.indir + "FakesEtaUncorrelated_{ch}.root".format(ch=charge)
nFakesEtaUncorrelated = 0
ff = ROOT.TFile.Open(ffile,"READ")
if not ff or not ff.IsOpen():
    raise RuntimeError('Unable to open file {fn}'.format(fn=ffile))
else:
    # count number of histograms and divide by 2 (there are up and down variations)
    nFakesEtaUncorrelated = ff.GetNkeys()/2
ff.Close()

if nFakesEtaUncorrelated:
    for i in range(1,nFakesEtaUncorrelated+1):
        syst = "FakesEtaUncorrelated{d}{fl}{ch}".format(d=i, fl=flavour, ch=charge)
        if isExcludedNuisance(excludeNuisances, syst): continue
        allSystForGroups.append(syst)
        card.write(('%-16s shape' % syst) + " ".join([kpatt % ("1.0" if "fakes" in p else "-") for p in allprocesses]) +"\n")        

ffile = options.indir + "FakesPtUncorrelated_{ch}.root".format(ch=charge)
nFakesPtUncorrelated = 0
ff = ROOT.TFile.Open(ffile,"READ")
if not ff or not ff.IsOpen():
    raise RuntimeError('Unable to open file {fn}'.format(fn=ffile))
else:
    # count number of histograms and divide by 2 (there are up and down variations)
    nFakesPtUncorrelated = ff.GetNkeys()/2
ff.Close()

if nFakesPtUncorrelated:
    for i in range(1,nFakesPtUncorrelated+1):
        syst = "FakesPtUncorrelated{d}{fl}{ch}".format(d=i, fl=flavour, ch=charge)
        if isExcludedNuisance(excludeNuisances, syst): continue
        allSystForGroups.append(syst)
        card.write(('%-16s shape' % syst) + " ".join([kpatt % ("1.0" if "fakes" in p else "-") for p in allprocesses]) +"\n")        


# fakes
fakeSysts = ["CMS_We_FRe_slope", "CMS_We_FRe_continuous"] if flavour == "el" else ["CMS_Wmu_FRmu_slope", "CMS_Wmu_FRmu_continuous"]
#fakeSysts = ["CMS_We_FRe_slope"] if flavour == "el" else ["CMS_Wmu_FRmu_slope"]
for syst in fakeSysts:
    if isExcludedNuisance(excludeNuisances, syst): continue
    allSystForGroups.append(syst)
    card.write(('%-16s shape' % syst) + " ".join([kpatt % ("1.0" if "fakes" in p else "-") for p in allprocesses]) +"\n")

# this is only for theory uncertainties that affect the cross section
sortedTheoSystkeys = []

procQCDunbin = []
if options.unbinnedQCDscaleZ: procQCDunbin.append("Z")
if options.unbinnedQCDscaleW: procQCDunbin.append(signalMatch)

# QCD scales unbinned
qcdUnbinned = ["muR", "muF", "muRmuF"] 
if len(procQCDunbin):
    for syst in qcdUnbinned:
        if isExcludedNuisance(excludeNuisances, syst): continue
        allSystForGroups.append(syst)
        card.write(('%-16s shape' % syst) + " ".join([kpatt % ("1.0" if any(x in p for x in procQCDunbin) else "-") for p in allprocesses]) +"\n")
        if options.unbinnedQCDscaleW: sortedTheoSystkeys.append(syst)

# W and Z common systematics
WandZ = [signalMatch, "Z"]
qcdAndPDF = ["pdf%d" % i for i in range(1,61)]
qcdAndPDF.append("alphaS")
for syst in qcdAndPDF:
    if isExcludedNuisance(excludeNuisances, syst): continue
    nSigma = "1.0"
    if "alphaS" in syst:
        # the alphaS variations should be scaled so that one sigma corresponds to +-0.0015 (weights correspond to +-0.001)
        nSigma = "0.67"
    allSystForGroups.append(syst)
    card.write(('%-16s shape' % syst) + " ".join([kpatt % (nSigma if any(x in p for x in WandZ) else "-") for p in allprocesses]) +"\n")
    sortedTheoSystkeys.append(syst)

# W only
if not isExcludedNuisance(excludeNuisances, "mW"): 
    allSystForGroups.append("mW")
    card.write(('%-16s shape' % "mW") + " ".join([kpatt % ("1.0" if signalMatch in p else "-") for p in allprocesses]) +"\n")
    sortedTheoSystkeys.append("mW")

qcdScale_wptBins = [] 
for i in range(1,11):
    qcdScale_wptBins.append("muR%d" % i)
    qcdScale_wptBins.append("muF%d" % i)
    qcdScale_wptBins.append("muRmuF%d" % i)
for syst in qcdScale_wptBins:
    if isExcludedNuisance(excludeNuisances, syst): continue
    allSystForGroups.append(syst)
    card.write(('%-16s shape' % syst) + " ".join([kpatt % ("1.0" if signalMatch in p else "-") for p in allprocesses]) +"\n")
    sortedTheoSystkeys.append(syst)
    

wExpSysts = ["CMS_We_sig_lepeff", "CMS_We_elescale"] if flavour == "el" else ["CMS_Wmu_sig_lepeff", "CMS_Wmu_muscale"]
for syst in wExpSysts:
    if isExcludedNuisance(excludeNuisances, syst): continue
    allSystForGroups.append(syst)
    card.write(('%-16s shape' % syst) + " ".join([kpatt % ("1.0" if any(x in p for x in WandZ) else "-") for p in allprocesses]) +"\n")

#effstatOffset = 25 if genBins.Neta == 24 else 26  ## FIXME: doesn't work if the binning is not 0.1 wide in eta
#effstatOffset = 25 if genBins.etaBins[-1] < 2.45 else 26  ## FIXME: it assumes the range extends up to 2.4 or 2.5
EffStat_systs = []
#nSystEffStat = int(2* (genBins.etaBins[-1] + 0.001) * 10)  # this allows to have 48 nuisances for electrons when gen_eta arrives to 2.4 (even if reco gets up to 2.5)
#effstatOffset = 1 + int( (genBins.etaBins[-1] + 0.001) * 10)
effstatOffset = 25 if flavour == "mu" else 26
nSystEffStat = 48 if flavour == "mu" else 50
for ipar in range(3):
    for ietabin in range(1, 1+nSystEffStat):        # there are 48 (or 50) etabins from 1 to 48 (or 50)
        syst = "ErfPar%dEffStat%d" % (ipar,ietabin)
        syst += "{fl}{ch}".format(fl=flavour,ch=charge)
        if isExcludedNuisance(excludeNuisances, syst): continue
        etaEffStat = ietabin - effstatOffset # assess whether it is in the first half, corresponding to negative eta            
        # since ietabin goes from 1 to XX, make etaEffStat goes from 0 to XX                 
        if etaEffStat < 0:
            etaEffStat = abs(etaEffStat) - 1
        # we always have 48 or 50 efficiency bins, but the reco binning might be coarser: get the eta for the efficiency bin
        # a template bin might have more than 1 efficiency variation if binning is coarser
        etaBinCenter = etaEffStat * 0.1 + 0.05  
        ietaTemplate = getArrayBinNumberFromValue(genBins.etaBins,etaBinCenter)  
        # if genBins extends below the reco, the returned value is negative, so no match for signal
        # for outliers, must also check the reco binning

        # if the reco binning along eta is narrower than the EffStat histogram used for the reweighting, skip this etaEffStat              
        # this happens for example for bin 1 and 50 in the electron channel if the reco binning (and therefore also the gen) stops at |eta|=2.4    
        if etaBinCenter < recoBins.etaBins[0] or etaBinCenter > recoBins.etaBins[-1]:
            continue

        EffStat_systs.append(syst)
        allSystForGroups.append(syst)
        matchesForEffStat = ["outliers", "_ieta_%d_" % ietaTemplate]
        if not options.noEffStatZ: matchesForEffStat.append("Z")
        #card.write(('%-16s shape' % syst) + " ".join([kpatt % ("1.0" if (signalMatch in p and any(x in p for x in matchesForEffStat)) else "-") for p in allprocesses]) +"\n")
        card.write(('%-16s shape' % syst) + " ".join([kpatt % ("1.0" if any(x in p for x in matchesForEffStat) else "-") for p in allprocesses]) +"\n")

card.write("\n")
if not isExcludedNuisance(excludeNuisances, "CMS_lumi_13TeV"): card.write("luminosity group = CMS_lumi_13TeV\n\n")
#if not isExcludedNuisance(excludeNuisances, "mW"): card.write("wmass group = mW\n\n")
card.write("pdfs group = "       + ' '.join(filter(lambda x: re.match('pdf.*',x),allSystForGroups)) + "\n\n")
card.write("QCDTheo group = "    + ' '.join(filter(lambda x: re.match('muR.*|muF.*|alphaS',x),allSystForGroups)) + "\n\n")
card.write("lepScale group = "   + ' '.join(filter(lambda x: re.match('CMS.*(ele|mu)scale',x),allSystForGroups)) + "\n\n")
card.write("EffStat group = "    + ' '.join(filter(lambda x: re.match('.*ErfPar\dEffStat.*',x),allSystForGroups)) + "\n\n")
card.write("Fakes group = "      + ' '.join(filter(lambda x: re.match('.*FR.*(norm|lnN|continuous)',x),allSystForGroups) +
                                            filter(lambda x: re.match('Fakes.*Uncorrelated.*',x),allSystForGroups)) + "\n\n")
card.write("OtherBkg group = "   + ' '.join(filter(lambda x: re.match('CMS_DY|CMS_Top|CMS_VV|CMS_Tau|CMS_We_flips|CMS_Wbkg',x),allSystForGroups)) + " \n\n")
card.write("OtherExp group = "   + ' '.join(filter(lambda x: re.match('CMS.*lepVeto|CMS.*bkg_lepeff',x),allSystForGroups)) + " \n\n")
card.write("EffSyst group = "    + ' '.join(filter(lambda x: re.match('CMS.*sig_lepeff',x),allSystForGroups)) + " \n\n")
card.write("\n")
card.write("\n")

## before closing the card, we will add other stuff
## then we will make the cross section root file
# we need a list of signal processes, specifying which ones are inside acceptance

## first make a list of all the signal processes
#tmp_sigprocs = [p for p in allprocesses if 'Wminus' in p or 'Wplus' in p]
tmp_sigprocs = []
isInAccProc = {}
for p in allprocesses:
    if 'Wminus' in p or 'Wplus' in p:
        # if outliers is a background, remove from xsec card
        if options.sig_out_bkg and "outliers" in p:
            pass
        else:
            ieta,ipt = get_ieta_ipt_from_process_name(p)    
            if ((hasPtRangeBkg and ptBinIsBackground[ipt]) or (hasEtaRangeBkg and etaBinIsBackground[ieta])):
                pass
            else:
                tmp_sigprocs.append(p)
                if hasEtaRangeOutAcc or options.sig_out_outAcc:
                    if "outliers" in p:
                        isInAccProc[p] = False if options.sig_out_outAcc else True
                    else:                    
                        if etaBinIsOutAcc[ieta]:
                            isInAccProc[p] = False
                        else:
                            isInAccProc[p] = True
                else:
                    isInAccProc[p] = True

# now adding additional stuff for charge asymmetry, and pt-integrated cross section
# actually, this would only work for the charge-combined card, but it is easier to have it here, so to use combineCards.py later

for p in sorted(isInAccProc.keys(), key= lambda x: get_ieta_ipt_from_process_name(x) if ('_ieta_' in x and '_ipt_' in x) else 0):
        newp = p.replace("plus","").replace("minus","")        
        tmpp = p.replace("plus","TMP").replace("minus","TMP")        
        tmpline = "{p} {m}".format(p=tmpp.replace('TMP','plus'), m=tmpp.replace('TMP','minus'))
        card.write("{np} chargeGroup = {bg}\n".format(np=newp, bg=tmpline )) 
card.write("\n")

# xsec inclusive in pt
for ch in ["plus", "minus"]:
    for ieta in range(genBins.Neta):
        procsThisIeta = filter( lambda x: re.match('.*_ieta_{ieta}_.*'.format(ieta=ieta),x), isInAccProc.keys() )        
        procsThisIeta = sorted(procsThisIeta, key= lambda x: get_ieta_ipt_from_process_name(x) if ('_ieta_' in x and '_ipt_' in x) else 0)
        newp = "W{ch}_{fl}_ieta_{ieta}_W{ch}_{fl}".format(ch=ch, fl=flavour, ieta=str(ieta))
        tmpnames = [x.replace("plus","TMP").replace("minus","TMP") for x in procsThisIeta]
        card.write("{np} sumGroup = {bg}\n".format(np=newp, bg=' '.join(x.replace("TMP",ch) for x in tmpnames) )) 
    card.write("\n")
card.write("\n")

for ieta in range(genBins.Neta):
    newp = "W_{fl}_ieta_{ieta}_W_{fl}".format(fl=flavour, ieta=str(ieta))
    chpair = "Wplus_{fl}_ieta_{ieta}_Wplus_{fl} Wminus_{fl}_ieta_{ieta}_Wminus_{fl}".format(ch=ch, fl=flavour, ieta=str(ieta))
    card.write("{np} chargeMetaGroup = {bg}\n".format(np=newp, bg=chpair )) 

        

card.write("\n")
card.write("## THE END!\n")
card.close()
    
print ""
print "Wrote datacard in %s" % cardname
print ""

# now xsec card
print "Now making cross section shape file and datacard"
print ""

## here we make a second datacard that will be masked. which for every process                                               
## has a 1-bin histogram with the cross section for every nuisance parameter and                                             
## every signal process inside                                                                                               

## xsecfilename                                                                                           
xsecfile = "/afs/cern.ch/work/m/mciprian/public/whelicity_stuff/xsection_genAbsEtaPt_dressed_mu_pt0p5_eta0p1_etaGap_yields.root"
# FIXME: following file has pt binning with width = 1GeV!
if options.xsecMaskedYields:
    xsecfile = "/afs/cern.ch/work/m/mciprian/public/whelicity_stuff/xsection_genAbsEtaPt_dressed_mu_pt1_eta0p1_etaGap_xsecPb.root"
if options.preFSRxsec:
    xsecfile = xsecfile.replace("_dressed_","_preFSR_")
hists = getXsecs_etaPt(tmp_sigprocs,
                       [i for i in sortedTheoSystkeys], 
                       binning,
                       xsecfile,
                       usePreFSR = True if options.preFSRxsec else False
                       )
tmp_xsec_histfile_name = shapefile.replace('_shapes.root','_shapes_xsec.root')
tmp_xsec_hists = ROOT.TFile(tmp_xsec_histfile_name, 'recreate')
for hist in hists:
    hist.Write()
tmp_xsec_hists.Close()
print "Created root file with cross sections: %s" % tmp_xsec_histfile_name

maskedChannels = ['InAcc']
if hasEtaRangeOutAcc: maskedChannels.append('OutAcc')
maskedChannelsCards = {}
for maskChan in maskedChannels:
    if maskChan=='InAcc': tmp_sigprocs_mcha = [p for p in tmp_sigprocs if isInAccProc[p]]
    else:                 tmp_sigprocs_mcha = [p for p in tmp_sigprocs if not isInAccProc[p]]
    tmp_xsec_dc_name = os.path.join(options.indir,'{bin}_{ch}_xsec_{acc}_card.txt'.format(bin=binname, ch=charge, acc=maskChan))
    maskedChannelsCards['{bin}_{ch}_xsec_{mc}'.format(bin=binname,ch=charge,mc=maskChan)] = tmp_xsec_dc_name
    tmp_xsec_dc = open(tmp_xsec_dc_name, 'w')
    tmp_xsec_dc.write("imax 1\n")
    tmp_xsec_dc.write("jmax *\n")
    tmp_xsec_dc.write("kmax *\n")
    tmp_xsec_dc.write('##----------------------------------\n')
    tmp_xsec_dc.write("shapes *  *  %s %s\n" % (tmp_xsec_histfile_name, 'x_$PROCESS x_$PROCESS_$SYSTEMATIC'))
    tmp_xsec_dc.write('##----------------------------------\n')
    tmp_xsec_dc.write('bin {b}\n'.format(b=binname))
    tmp_xsec_dc.write('observation -1\n') ## don't know if that will work...                                                     
    tmp_xsec_dc.write('bin      {s}\n'.format(s=' '.join(['{b}'.format(b=binname) for p in tmp_sigprocs_mcha])))
    tmp_xsec_dc.write('process  {s}\n'.format(s=' '.join([p for p in tmp_sigprocs_mcha])))
    tmp_xsec_dc.write('process  {s}\n'.format(s=' '.join([str(procNum[pname])  for pname in tmp_sigprocs_mcha])))
    tmp_xsec_dc.write('rate     {s}\n'.format(s=' '.join('-1' for i in range(len(tmp_sigprocs_mcha)))))
    tmp_xsec_dc.write('# --------------------------------------------------------------\n')
    for sys in sortedTheoSystkeys: # this is only theoretical systs
        tmp_xsec_dc.write('%-15s   shape %s\n' % (sys,(" ".join(['1.0' if p in tmp_sigprocs_mcha  else '  -  ' for p in tmp_sigprocs_mcha]))) )
    tmp_xsec_dc.close()


## end of all the xsec construction of datacard and making the file                                                               
print "Wrote cross section datacard in %s" % tmp_xsec_dc_name
print ""
