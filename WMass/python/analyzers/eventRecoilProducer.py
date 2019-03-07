from PhysicsTools.Heppy.analyzers.core.Analyzer import Analyzer
from PhysicsTools.Heppy.analyzers.core.AutoHandle import AutoHandle
from PhysicsTools.HeppyCore.utils.deltar import * 
import PhysicsTools.HeppyCore.framework.config as cfg
import copy
import ROOT
import os
from math import hypot
from copy import deepcopy
from sklearn.decomposition import PCA
import numpy as np

class EventRecoilProducer(Analyzer):
    def __init__(self, cfg_ana, cfg_comp, looperName ):
        super(EventRecoilProducer,self).__init__(cfg_ana,cfg_comp,looperName)

        self.ptThr=0.5
        self.pvflag=ROOT.pat.PackedCandidate.PVTight
        self.metFlavours=['tkmet','npv_tkmet','closest_tkmet','puppimet','invpuppimet','gen_tkmet','gen_tkmet5','gen_allmet','gen_allmet5']

        print 'EventRecoilProducer',
        print 'Will use pT>{0} GeV and pvFlags>={1}'.format(self.ptThr,self.pvflag),
        print 'Producing variables for',self.metFlavours

        if "FastJetAnalysis_cc.so" not in ROOT.gSystem.GetLibraries():
            print "Compile FastJetAnalysis script"
            ROOT.gSystem.Load("/cvmfs/cms.cern.ch/slc6_amd64_gcc530/external/fastjet/3.1.0/lib/libfastjet.so")
            ROOT.gSystem.AddIncludePath("-I/cvmfs/cms.cern.ch/slc6_amd64_gcc630/external/fastjet/3.1.0/include")
            ROOT.gSystem.Load("/cvmfs/cms.cern.ch/slc6_amd64_gcc530/external/fastjet-contrib/1.020/lib/libfastjetcontribfragile.so")
            ROOT.gSystem.AddIncludePath("-I/cvmfs/cms.cern.ch/slc6_amd64_gcc630/external/fastjet-contrib/1.020/include")
            ROOT.gROOT.ProcessLine(".L %s/src/CMGTools/WMass/python/postprocessing/helpers/FastJetAnalysis.cc+" % os.environ['CMSSW_BASE'])
        else:
            print "FastJetAnalysis_cc.so found in ROOT libraries"

        self._worker = ROOT.FastJetAnalysis()

    def declareHandles(self):
        super(EventRecoilProducer, self).declareHandles()
        self.handles['cmgCand'] = AutoHandle( self.cfg_ana.pf, self.cfg_ana.pfType )
        self.mchandles['packedGen'] = AutoHandle( self.cfg_ana.gen, self.cfg_ana.genType )


    def beginLoop(self, setup):
        super(EventRecoilProducer,self).beginLoop(setup)


    def doPCA(self,momList):

        """perform a principal component analysis and returns the thrust vectors"""

        if len(momList)<2: return np.zeros(3)

        n_components=momList.shape[1]
        pcaAnalysis = PCA(n_components=n_components)
        pcaAnalysis.fit(momList)
        
        #project along the thrust axis and sort
        thrust = [ np.sum( np.absolute(np.dot(momList,pcaAnalysis.components_[i])) ) for i in xrange(0,n_components) ]
        total_sum = np.sum( np.sqrt( np.sum( momList**2, axis=1) ) )
        thrust = thrust/total_sum
        thrust = np.sort(thrust)

        return thrust
    
    def analyzeMomentumTensor(self,momList,r=1):

        """compute the momentum tensor and its eigenvalues"""
        
        toReturn=[-1,-1,-1,-1,-1]
        if len(momList)<2: return toReturn

        #momentum tensor
        momTensor=np.zeros((3,3))
        norm=0
        tmomTensor=np.zeros((2,2))
        normT=0        
        for i in xrange(0,len(momList)):

            X,Y,Z=momList[i]
            p3=np.sqrt(X**2+Y**2+Z**2)
            if p3>0:
                coeff = np.power(p3,r-2 )
                norm += np.power(p3,r)
                momTensor[0][0] += coeff*X*X
                momTensor[0][1] += coeff*X*Y
                momTensor[0][2] += coeff*X*Z
                momTensor[1][0] += coeff*Y*X
                momTensor[1][1] += coeff*Y*Y
                momTensor[1][2] += coeff*Y*Z
                momTensor[2][0] += coeff*Z*X
                momTensor[2][1] += coeff*Z*Y
                momTensor[2][2] += coeff*Z*Z

            p2 = np.sqrt(X*X+Y*Y)
            if p2>0:
                coeff = np.power(p2,r-2)
                normT += np.power(p2,r)
                tmomTensor[0][0] += coeff*X*X
                tmomTensor[0][1] += coeff*X*Y
                tmomTensor[1][0] += coeff*Y*X
                tmomTensor[1][1] += coeff*Y*Y
                
        momTensor=momTensor/norm
        tmomTensor=tmomTensor/normT

        #eigenvalues
        w,_=np.linalg.eig(momTensor)
        w=np.sort(w)        
        toReturn[0]=1.5*(w[0]+w[1])                    #sphericity
        toReturn[1]=1.5*w[0]                           #aplanarity
        toReturn[2]=3.*(w[2]*w[1]+w[2]*w[1]+w[1]*w[0]) #C
        toReturn[3]=27.*w[0]*w[1]*w[2]                 #D
        toReturn[4]=np.linalg.det(tmomTensor)          #detST

        return toReturn

    def processGen(self,event,etacut=2.4,ptcut=-1,includeNeutrals=False):

        """makes a charged-based gen recoil estimator"""

        if ptcut < 0:
            ptcut = self.ptThr
        
        #loop over final state particles
        pMom=[]
        try:
            nlep=0
            for p in self.mchandles['packedGen'].product():
                if not includeNeutrals and p.charge() == 0:
                    continue
                if abs(p.pdgId()) in [12,14,16]: #veto neutrinos
                    continue
                if p.status() != 1: continue
                if p.pt()<ptcut or abs(p.eta())>etacut : continue

                #veto up to two high pT central, leptons
                if abs(p.pdgId()) in [11,13] and p.pt()>20 and abs(p.eta())<etacut:
                    nlep+=1
                    if nlep<=2 : continue

                pMom.append( [p.px(),p.py(),p.pz(),p.pt(),p.energy()] )
        except:
            pass

        return np.array(pMom)

    def process(self, event):

        """process event, return True (go to next module) or False (fail, go to next event)"""

        self.readCollections(event.input)

        #gen level
        genMom=self.processGen(event)
        genMom5=self.processGen(event, etacut=5.)
        genMomAll=self.processGen(event, includeNeutrals=True)
        genMomAll5=self.processGen(event, etacut=6., ptcut=0., includeNeutrals=True)

        #vertex analysis
        mindz=9999.
        next2pv=-1
        for ivtx in xrange(1,len(event.goodVertices)):            
            dz=event.goodVertices[ivtx].position().z()-event.goodVertices[0].position().z()
            if abs(dz)>abs(mindz): continue
            mindz=dz
            next2pv=ivtx
        setattr(event,'mindz',mindz)
        setattr(event,'vx',event.goodVertices[0].position().x())
        setattr(event,'vy',event.goodVertices[0].position().y())
        setattr(event,'vz',event.goodVertices[0].position().z())

        #pre-select leptons
        vetoCands=[]
        for l in event.selectedLeptons:
            if l.pt()<20 : continue
            vetoCands.append(l)

        #select pf candidates
        pfTags,pfMom,pfWeights,pfCov=[],[],[],[]
        pfcands = self.handles['cmgCand'].product()
        for pfcand in pfcands:

            p=pfcand.p4()
            if p.pt()<self.ptThr : continue

            #veto up to two of the selected leptons 
            #if it's in a R=0.1 cone, and the difference in pT is <50% 
            #any pfcandidate is considered (l -> l gamma in PU may generate some PF confusion)
            veto=False
            for ic in xrange(0,min(2,len(vetoCands))):
                if deltaR(vetoCands[ic].p4(),p)>0.1: continue
                dpt=abs(1-vetoCands[ic].pt()/p.pt())
                if dpt>0.5: continue
                veto=True
                break
            if veto: continue


            #flags to be used in the different met flavours
            isCharged=True if pfcand.charge()!=0 else False
            isCentral=True if abs(p.eta())<2.4 else False
            isFromPV=True if pfcand.fromPV()>=self.pvflag else False
            isFromNext2PV=True if not isFromPV and next2pv>0 and pfcand.fromPV(next2pv)>=self.pvflag else False
            use_tkmet         = (isCharged and isCentral and isFromPV)
            use_npv_tkmet     = (isCharged and isCentral and not isFromPV)
            use_closest_tkmet = (isCharged and isCentral and isFromNext2PV)
            use_puppimet      = True
            use_invpuppimet   = True

            #add to list
            pfTags.append( [use_tkmet,use_npv_tkmet,use_closest_tkmet,use_puppimet,use_invpuppimet] )
            pfMom.append( [pfcand.px(),pfcand.py(),pfcand.pz(),pfcand.pt(),pfcand.energy()] )
            pfWeights.append( [pfcand.puppiWeightNoLep()] )
            
            # resolutions
            dpt,dph = 0,0
            cov_xx,cov_xy,cov_yy = 0,0,0
            energy = pfcand.energy()
            c = pfcand.px()/pfcand.pt();
            s = pfcand.py()/pfcand.pt();
            # tracks
            if isCharged:
                dpt = pfcand.pseudoTrack().ptError()
                dph = pfcand.pseudoTrack().phiError()
            # ECAL (photons)
            # arXiv:1306.2016: s/E = sqrt(0.028**2/E + (0.12/E)**2 + 0.003**2)
            # The achieved position resolution in EB (EE) is 3 (5) mrad in phi <- no pt given
            # Technical proposal: sigma_phi < 50 mrad/sqrt(E)
            elif pfcand.pdgId() == 22:
                dph = 0.050/math.sqrt(energy)
                if abs(pfcand.eta()) < 1.479:
                    dpt = pfcand.pt() * math.sqrt(0.028**2/energy + (0.12/energy)**2 + 0.003**2)
                else: # factor 2 for endcaps according to technical proposal
                    dpt = pfcand.pt() * math.sqrt(0.056**2/energy + (0.24/energy)**2 + 0.006**2)
            # HCAL (neutral hadrons)
            # arXiv: 0911.4991: s/E = sqrt(0.847**2/E + 0.074**2)
            elif abs(pfcand.pdgId()) > 10:
                dpt = pfcand.pt() * math.sqrt(0.847**2/energy + 0.074**2)
                dph = 0.050/math.sqrt(energy) * 0.0873/0.0174 # assume scaling with crystal/tile size
                if abs(pfcand.eta()) > 1.74:
                    dph *= 2
            # HF: s/E = sqrt(1.98**2/E + 0.09**2)
            elif abs(pfcand.pdgId()) < 10:
                dpt = pfcand.pt() * math.sqrt(1.98**2/energy + 0.09**2)
                dph = 0.050/math.sqrt(energy) * 0.0873/0.0174 * 2
                if abs(pfcand.eta()) > 4.7:
                    dph *= 2
            
            cov_xx += dpt*dpt*c*c + dph*dph*s*s;
            cov_xy += (dpt*dpt-dph*dph)*c*s;
            cov_yy += dph*dph*c*c + dpt*dpt*s*s;
            
            #print('resolution', pfcand.pdgId(), pfcand.charge(), pfcand.pt(), energy, dpt, dph)
            pfCov.append( [cov_xx,cov_xy,cov_yy] )
            
        #convert to numpy arrays for filtering and other operations
        pfTags=np.array(pfTags)
        pfMom=np.array(pfMom)
        pfWeights=np.array(pfWeights)
        pfCov=np.array(pfCov)

        #produce the observables for each met flavour
        tkmet_phi=None
        for im in xrange(0,len(self.metFlavours)):            

            m=self.metFlavours[im]
            
            selPF=[]
            selCov = np.array([[ 0., 0., 0.],[ 0., 0., 0.]], dtype=np.float32) #dummy values
            if m=='gen_tkmet':
                selPF=genMom
            elif m=='gen_tkmet5':
                selPF=genMom5
            elif m=='gen_allmet':
                selPF=genMomAll
            elif m=='gen_allmet5':
                selPF=genMomAll5
            else:
                mfilter=(pfTags[:,im]==True)
                selPF=pfMom[mfilter] 
                selCov=pfCov[mfilter]
                wgtSum=1.0
                if 'puppi' in m:
                    selPF_w=pfWeights[mfilter]  
                    if 'invpuppi' in m: selPF_w=abs(1.0-selPF_w)
                    selPF=selPF*selPF_w
                    selCov=selCov*selPF_w
                    
                    #some will be scaled to 0 with puppi weights => filter them out
                    ptfilter=(selPF[:,3]>self.ptThr)
                    selPF=selPF[ptfilter]
                    selCov=selCov[ptfilter]
                            
            #basic kinematics
            sig = 0
            if len(selPF)>0:
                recx,recy,recz,ht,_=np.sum(selPF,axis=0,dtype=np.float32)
                recpt=np.hypot(recx,recy)
                recphi=np.arctan2(recy,recx)
                leadmom=selPF[np.argmax(selPF[:,3])]
                leadpt=leadmom[3]
                leadphi=np.arctan2(leadmom[1],leadmom[0])
                scalar_sphericity=recpt/ht
                # MET significance
                cov_xx,cov_xy,cov_yy=np.sum(selCov,axis=0,dtype=np.float32)
                # covariance matrix determinant
                det = cov_xx*cov_yy - cov_xy*cov_xy + 1e-5
                # invert matrix
                ncov_xx = cov_yy / det;
                ncov_xy = -cov_xy / det;
                ncov_yy = cov_xx / det;
                # product of met and inverse of covariance
                sig = recx*recx*ncov_xx + 2*recx*recy*ncov_xy + recy*recy*ncov_yy;
            else:
                recpt=0
                recphi=0
                leadpt=0
                leadphi=0
                ht=0
                scalar_sphericity=0

            if im==0: tkmet_phi=recphi
            dphi2tkmet=ROOT.TVector2.Phi_mpi_pi(recphi-tkmet_phi)

            setattr(event,'h%s_n'%m,len(selPF))
            setattr(event,'h%s_pt'%m,float(recpt))
            setattr(event,'h%s_phi'%m,float(recphi))
            setattr(event,'h%s_leadpt'%m,float(leadpt))
            setattr(event,'h%s_leadphi'%m,float(leadphi))
            setattr(event,'h%s_scalar_ht'%m,float(ht))
            setattr(event,'h%s_scalar_sphericity'%m,float(scalar_sphericity))
            setattr(event,'h%s_dphi2tkmet'%m,float(dphi2tkmet))
            setattr(event,'h%s_cov_xx'%m,float(cov_xx))
            setattr(event,'h%s_cov_xy'%m,float(cov_xy))
            setattr(event,'h%s_cov_yy'%m,float(cov_yy))
            setattr(event,'h%s_sig'%m,float(sig))

            #thrust variables and event shapes (if no PF candidates -1 is assigned)
            try:
                Thrust3D=self.doPCA(momList=selPF[:,[0,1,2]])
                Thrust2D=self.doPCA(momList=selPF[:,[0,1]])            
                sphericity,aplanarity,C,D,detST=self.analyzeMomentumTensor(momList=selPF[:,[0,1,2]],r=1)
            except:
                Thrust3D=[-1,-1,-1]
                Thrust2D=[-1,-1]
                sphericity,aplanarity,C,D,detST=-1,-1,-1,-1,-1
            setattr(event,"h%s_thrust"%m, float(Thrust3D[2]))
            setattr(event,"h%s_thrustMajor"%m, float(Thrust3D[1]))
            setattr(event,"h%s_thrustMinor"%m, float(Thrust3D[0]))
            setattr(event,"h%s_oblateness"%m, float(Thrust3D[1]-Thrust3D[0]))            
            setattr(event,"h%s_thrustTransverse"%m, float(Thrust2D[1]))
            setattr(event,"h%s_thrustTransverseMinor"%m, float(Thrust2D[0]))
            setattr(event,"h%s_sphericity"%m, float(sphericity))
            setattr(event,"h%s_aplanarity"%m, float(aplanarity))
            setattr(event,"h%s_C"%m, float(C))
            setattr(event,"h%s_D"%m, float(D))
            setattr(event,"h%s_detST"%m, float(detST))

            #N-jetttiness and rho
            self._worker.reset()
            for i in xrange(0,len(selPF)):
                px,py,pz,pt,en=selPF[i]
                self._worker.add(px,py,pz,en)
            self._worker.run()
            setattr(event,"h%s_rho"%m, self._worker.rho())
            for i in xrange(1,5):
                setattr(event,"h%s_tau%d"%(m,i), self._worker.tau(i))

        return True


setattr(EventRecoilProducer,
        "defaultConfig", 
        cfg.Analyzer(class_object = EventRecoilProducer,
                     pf='packedPFCandidates',
                     pfType='std::vector<pat::PackedCandidate>',
                     gen='packedGenParticles', 
                     genType='std::vector<pat::PackedGenParticle>')
        )
