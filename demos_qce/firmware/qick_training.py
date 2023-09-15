from qick.qick import *

from drivers.pfb import *
from drivers.dds import *
from drivers.misc import *

import numpy as np

class AnalysisChain():
    # Event dictionary.
    event_dict = {
        'source' :
        {
            'immediate' : 0,
            'slice' : 1,
            'tile' : 2,
            'sysref' : 3,
            'marker' : 4,
            'pl' : 5,
        },
        'event' :
        {
            'mixer' : 1,
            'coarse_delay' : 2,
            'qmc' : 3,
        },
    }
    
    # Mixer dictionary.
    mixer_dict = {
        'mode' : 
        {
            'off' : 0,
            'complex2complex' : 1,
            'complex2real' : 2,
            'real2ccomplex' : 3,
            'real2real' : 4,
        },
        'type' :
        {
            'coarse' : 1,
            'fine' : 2,
            'off' : 3,
        }}
    
    # Constructor.
    def __init__(self, soc, chain):
        # Sanity check. Is soc the right type?
        if isinstance(soc, QickTrainingSoc) == False:
            raise RuntimeError("%s (QickTraining, AnalysisChain)" % __class__.__name__)
        else:
            # Soc instance.
            self.soc = soc
            
            # Sanity check. Is this a sythesis chain?
            if chain['type'] != 'analysis':
                raise RuntimeError("An \'analysis\' chain must be provided")
            else:
                # Dictionary.
                self.dict = {}

                # Analysis chain.
                self.dict['chain'] = chain

                # Update settings.
                self.update_settings()
                    
                # pfb block.
                pfb = getattr(self.soc, self.dict['chain']['pfb'])

                # Does the chain has a kidsim?
                if pfb.HAS_KIDSIM:
                    # Frequency resolution (MHz).
                    kidsim = getattr(self.soc, self.dict['chain']['kidsim'])
                    self.dict['fr'] = kidsim.DF_DDS/1e6
 
    def update_settings(self):
        tile = int(self.dict['chain']['adc']['tile'])
        ch = int(self.dict['chain']['adc']['ch'])
        m_set = self.soc.rf.adc_tiles[tile].blocks[ch].MixerSettings
        id_ = self.dict['chain']['adc']['id']
        self.dict['mixer'] = {
            'mode'     : self.return_key(self.mixer_dict['mode'], m_set['MixerMode']),
            'type'     : self.return_key(self.mixer_dict['type'], m_set['MixerType']),
            'evnt_src' : self.return_key(self.event_dict['source'], m_set['EventSource']),
            'freq'     : -self.soc.adcs[id_]['fs']/4
        }
        
        self.dict['nqz'] = self.soc.rf.adc_tiles[tile].blocks[ch].NyquistZone        

    def get_mixer_frequency(self):
        return self.dict['mixer']['freq']
        
    def return_key(self,dictionary,val):
        for key, value in dictionary.items():
            if value==val:
                return key
        return('Key Not Found')
    
    def freq2ch(self, f):
        # Get blocks.
        pfb_b = getattr(self.soc, self.dict['chain']['pfb'])
        
        # Sanity check: is frequency on allowed range?
        fmix = abs(self.dict['mixer']['freq'])
        fs = self.dict['chain']['fs']
              
        if (fmix-fs/2) < f < (fmix+fs/2):
            f_ = f - fmix
            return pfb_b.freq2ch(f_)
        else:
            raise ValueError("Frequency value %f out of allowed range [%f,%f]" % (f,fmix-fs/2,fmix+fs/2))

    def ch2freq(self, ch):
        # Get blocks.
        pfb_b = getattr(self.soc, self.dict['chain']['pfb'])

        # Mixer frequency.
        fmix = abs(self.dict['mixer']['freq'])
        f = pfb_b.ch2freq(ch) 
        
        return f+fmix
    
    def qout(self,q):
        pfb = getattr(self.soc, self.dict['chain']['pfb'])
        pfb.qout(q)
        
    @property
    def fs(self):
        return self.dict['chain']['fs']
    
    @property
    def fc_ch(self):
        return self.dict['chain']['fc_ch']
    
    @property
    def fs_ch(self):
        fs_ch = self.dict['chain']['fs_ch']
        dec = self.decimation
        return fs_ch/dec

    @property
    def fr(self):
        return self.dict['fr']
    
    @property
    def name(self):
        return self.dict['chain']['name']
    
class SynthesisChain():
    # Event dictionary.
    event_dict = {
        'source' :
        {
            'immediate' : 0,
            'slice' : 1,
            'tile' : 2,
            'sysref' : 3,
            'marker' : 4,
            'pl' : 5,
        },
        'event' :
        {
            'mixer' : 1,
            'coarse_delay' : 2,
            'qmc' : 3,
        },
    }
    
    # Mixer dictionary.
    mixer_dict = {
        'mode' : 
        {
            'off' : 0,
            'complex2complex' : 1,
            'complex2real' : 2,
            'real2ccomplex' : 3,
            'real2real' : 4,
        },
        'type' :
        {
            'coarse' : 1,
            'fine' : 2,
            'off' : 3,
        }}    

    # Constructor.
    def __init__(self, soc, chain):
        # Sanity check. Is soc the right type?
        if isinstance(soc, QickTrainingSoc) == False:
            raise RuntimeError("%s (QickTraining, AnalysisChain)" % __class__.__name__)
        else:
            # Soc instance.
            self.soc = soc
            
            # Sanity check. Is this a sythesis chain?
            if chain['type'] != 'synthesis':
                raise RuntimeError("A \'synthesis\' chain must be provided")
            else:
                # Dictionary.
                self.dict = {}

                # Synthesis chain.
                self.dict['chain'] = chain

                # pfb block.
                pfb = getattr(self.soc, self.dict['chain']['pfb'])

                # Does this chain has a kidsim?
                if pfb.HAS_KIDSIM:
                    # Set frequency resolution (MHz).
                    kidsim = getattr(self.soc, self.dict['chain']['kidsim'])
                    self.dict['fr'] = kidsim.DF_DDS/1e6

                # Update settings.
                self.update_settings()

    def update_settings(self):
        tile = int(self.dict['chain']['dac']['tile'])
        ch = int(self.dict['chain']['dac']['ch'])
        m_set = self.soc.rf.dac_tiles[tile].blocks[ch].MixerSettings
        id_ = self.dict['chain']['dac']['id']
        self.dict['mixer'] = {
            'mode'     : self.return_key(self.mixer_dict['mode'], m_set['MixerMode']),
            'type'     : self.return_key(self.mixer_dict['type'], m_set['MixerType']),
            'evnt_src' : self.return_key(self.event_dict['source'], m_set['EventSource']),
            'freq'     : self.soc.dacs[id_]['fs']/4
        }
        
        self.dict['nqz'] = self.soc.rf.dac_tiles[tile].blocks[ch].NyquistZone        
        
    def return_key(self,dictionary,val):
        for key, value in dictionary.items():
            if value==val:
                return key
        return('Key Not Found')
    
    def freq2ch(self, f):
        # Get blocks.
        pfb_b = getattr(self.soc, self.dict['chain']['pfb'])
        
        # Sanity check: is frequency on allowed range?
        fmix = abs(self.dict['mixer']['freq'])
        fs = self.dict['chain']['fs']
                
        if (fmix-fs/2) < f < (fmix+fs/2):
            f_ = f - fmix
            return pfb_b.freq2ch(f_)

        else:
            raise ValueError("Frequency value %f out of allowed range [%f,%f]" %(f, fmix-fs/2, fmix+fs/2))          

    def ch2freq(self, ch):
        # Get blocks.
        pfb_b = getattr(self.soc, self.dict['chain']['pfb'])

        # Sanity check: is frequency on allowed range?
        fmix = abs(self.dict['mixer']['freq'])
        f = pfb_b.ch2freq(ch)
        
        return f+fmix
            
    # PFB quantization.
    def qout(self,q):
        pfb = getattr(self.soc, self.dict['chain']['pfb'])
        pfb.qout(q)
        
    @property
    def fs(self):
        return self.dict['chain']['fs']
    
    @property
    def fc_ch(self):
        return self.dict['chain']['fc_ch']
    
    @property
    def fs_ch(self):
        return self.dict['chain']['fs_ch']

    @property
    def fr(self):
        return self.dict['fr']
        
    @property
    def name(self):
        return self.dict['chain']['name']
    
class SimuChain():
    # Constructor.
    def __init__(self, soc, simu=None, name=""):
        # Sanity check. Is soc the right type?
        if isinstance(soc, QickTrainingSoc) == False:
            raise RuntimeError("%s (QickTraining, AnalysisChain)" % __class__.__name__)
        else:
            # Soc instance.
            self.soc = soc
            
            # Chain name.
            self.name = name

            # analysis/sinthesis chains to access functions.
            self.analysis   = AnalysisChain(self.soc, simu['analysis'])
            self.synthesis  = SynthesisChain(self.soc, simu['synthesis'])

            # Frequency resolution.
            fr_min = min(self.analysis.fr,self.synthesis.fr)
            fr_max = max(self.synthesis.fr,self.synthesis.fr)
            self.fr = fr_max

    def enable(self, f, t=None, N=None, verbose=False):
        # Config dictionary.
        cfg_ = {'sel' : 'resonator', 'freq' : f}
        if t is not None:
            cfg_['sweep_time'] = t
        if N is not None:
            cfg_['nstep'] = N
        self.set_resonator(cfg_, verbose=verbose)

    def disable(self, f, verbose=False):
        # Config dictionary.
        cfg_ = {'sel' : 'input', 'freq' : f}
        self.set_resonator(cfg_, verbose=verbose)

    def alloff(self, verbose=False):
        # Config dictionary.
        cfg_ = {'sel' : 'input'}

        # Kidsim block.
        kidsim_b = getattr(self.soc, self.analysis.dict['chain']['kidsim'])
        kidsim_b.setall(cfg_, verbose=verbose) 

    def set_resonator(self, cfg, verbose=False):
        # Get blocks.
        pfb_b       = getattr(self.soc, self.analysis.dict['chain']['pfb'])
        kidsim_b    = getattr(self.soc, self.analysis.dict['chain']['kidsim'])

        # Sanity check: is frequency on allowed range?
        fmix = abs(self.analysis.get_mixer_frequency())
        fs = self.analysis.fs
        f  = cfg['freq']
              
        if (fmix-fs/2) < f < (fmix+fs/2):
            f_ = f - fmix
            k = pfb_b.freq2ch(f_)

            # Compute resulting dds frequency.
            fdds = f_ - pfb_b.ch2freq(k)
            
            if verbose:
                print("{}: f = {} MHz, fd = {} MHz, k = {}, fdds = {} MHz".format(__class__.__name__, f, f_, k, fdds))

            # Update config structure.
            cfg['channel'] = k
            cfg['dds_freq'] = fdds

            # Set resonator.
            kidsim_b.set_resonator(cfg, verbose=verbose)
                
        else:
            raise ValueError("Frequency value %f out of allowed range [%f,%f]" % (f,fmix-fs/2,fmix+fs/2))

    def qout(self,q):
        self.analysis.qout(q)
        self.synthesis.qout(q)

class QickTrainingSoc(QickSoc, QickConfig):    

    # Constructor.
    def __init__(self, bitfile, force_init_clks=False, ignore_version=True, **kwargs):
        """
        Constructor method
        """
        QickSoc.__init__(self, bitfile, force_init_clks=force_init_clks, ignore_version=ignore_version, **kwargs)

        self.map_local()

        # Add triggers for Kidsim.
        for i in range(8):
            self['tprocs'][0]['output_pins'].append(('output',7,i+12, 'Resonator {}'.format(i)))

    def map_local(self):
        # PFB for Analysis.
        self.pfbs_in = []
        pfbs_in_drivers = set([AxisPfbAnalysis])

        # PFB for Synthesis.
        self.pfbs_out = []
        pfbs_out_drivers = set([AxisPfbSynthesis])

        # Populate the lists with the registered IP blocks.
        for key, val in self.ip_dict.items():
            if val['driver'] in pfbs_in_drivers:
                self.pfbs_in.append(getattr(self, key))
            elif val['driver'] in pfbs_out_drivers:
                self.pfbs_out.append(getattr(self, key))

        # Configure the drivers.
        for pfb in self.pfbs_in:
            adc = pfb.dict['adc']['id']
            pfb.configure(self.adcs[adc]['fs']/self.adcs[adc]['decimation'])

            # Does this pfb has a KIDSIM?
            if pfb.HAS_KIDSIM:
                block = getattr(self, pfb.dict['kidsim'])
                block.configure(pfb.dict['freq']['fb'])

        for pfb in self.pfbs_out:
            dac = pfb.dict['dac']['id']
            pfb.configure(self.dacs[dac]['fs']/self.dacs[dac]['interpolation'])

        self['adcs'] = list(self.adcs.keys())
        self['dacs'] = list(self.dacs.keys())
        self['analysis'] = []
        self['synthesis'] = []
        self['simu'] = []
        for pfb in self.pfbs_in:
            thiscfg = {}
            thiscfg['type'] = 'analysis'
            thiscfg['adc'] = pfb.dict['adc']
            thiscfg['pfb'] = pfb.fullpath
            if pfb.HAS_KIDSIM:
                thiscfg['subtype'] = 'sim'
                thiscfg['kidsim'] = pfb.dict['kidsim']
            thiscfg['fs'] = pfb.dict['freq']['fs']
            thiscfg['fs_ch'] = pfb.dict['freq']['fb']
            thiscfg['fc_ch'] = pfb.dict['freq']['fc']
            thiscfg['nch'] = pfb.dict['N']
            self['analysis'].append(thiscfg)

        for pfb in self.pfbs_out:
            thiscfg = {}
            thiscfg['type'] = 'synthesis'
            if pfb.HAS_KIDSIM:
                thiscfg['subtype'] = 'sim'
                thiscfg['kidsim'] = pfb.dict['kidsim']
            thiscfg['dac'] = pfb.dict['dac']
            thiscfg['pfb'] = pfb.fullpath
            thiscfg['fs'] = pfb.dict['freq']['fs']
            thiscfg['fs_ch'] = pfb.dict['freq']['fb']
            thiscfg['fc_ch'] = pfb.dict['freq']['fc']
            thiscfg['nch'] = pfb.dict['N']
            self['synthesis'].append(thiscfg)

        # Search for dual/simulation chains.
        for ch_a in self['analysis']:
            # Is it sim?
            if ch_a['subtype'] == 'sim':
                # Find matching chain (they share a axis_kidsim block).
                found = False
                kidsim = ch_a['kidsim']
                for ch_s in self['synthesis']:
                    # Is it sim?
                    if ch_s['subtype'] == 'sim':
                        if kidsim == ch_s['kidsim']:
                            found = True 
                            thiscfg = {}
                            thiscfg['analysis']  = ch_a
                            thiscfg['synthesis'] = ch_s
                            self['simu'].append(thiscfg)
                    
                # If not found print an error.
                if not found:
                    raise RuntimeError("Could not find dual chain for PFB {}".format(ch_a['pfb']))

        return
