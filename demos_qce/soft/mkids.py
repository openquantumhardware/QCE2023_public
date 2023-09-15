from qick.qick import *

from drivers.pfb import *
from drivers.dds import *
from drivers.misc import *

import numpy as np

class RFDC(xrfdc.RFdc):
    """
    Extends the xrfdc driver.
    Since operations on the RFdc tend to be slow (tens of ms), we cache the Nyquist zone and frequency.
    """
    bindto = ["xilinx.com:ip:usp_rf_data_converter:2.3",
              "xilinx.com:ip:usp_rf_data_converter:2.4",
              "xilinx.com:ip:usp_rf_data_converter:2.6"]

    def __init__(self, description):
        """
        Constructor method
        """
        super().__init__(description)
        # Dictionary for configuration.
        self.dict = {}

        # Initialize nqz and freq.
        self.dict['nqz']  = {'adc' : {}, 'dac' : {}}
        self.dict['freq'] = {'adc' : {}, 'dac' : {}}

    def configure(self, soc):
        self.dict['cfg'] = {'adc' : soc.adcs, 'dac' : soc.dacs}

    def set_mixer_freq(self, blockid, f, blocktype='dac'):
        # Get config.
        cfg = self.dict['cfg'][blocktype]

        # Check Nyquist zone.
        fs = cfg[blockid]['fs']
        if abs(f) > fs/2 and self.get_nyquist(blockid, blocktype)==2:
            fset *= -1

        # Get tile and channel from id.
        tile, channel = [int(a) for a in blockid]

        # Get Mixer Settings.
        if blocktype == 'adc':
            m_set = self.adc_tiles[tile].blocks[channel].MixerSettings
        elif blocktype == 'dac':
            m_set = self.dac_tiles[tile].blocks[channel].MixerSettings
        else:
            raise RuntimeError("Blocktype %s not recognized" & blocktype)

        # Make a copy of mixer settings.
        m_set_copy = m_set.copy()

        # Update the copy
        m_set_copy.update({
            'Freq': f,
            'PhaseOffset': 0})

        # Update settings.
        if blocktype == 'adc':
            self.adc_tiles[tile].blocks[channel].MixerSettings = m_set_copy
            self.adc_tiles[tile].blocks[channel].UpdateEvent(xrfdc.EVENT_MIXER)
            self.dict['freq'][blocktype][blockid] = f
        elif blocktype == 'dac':
            self.dac_tiles[tile].blocks[channel].MixerSettings = m_set_copy
            self.dac_tiles[tile].blocks[channel].UpdateEvent(xrfdc.EVENT_MIXER)
            self.dict['freq'][blocktype][blockid] = f
        else:
            raise RuntimeError("Blocktype %s not recognized" & blocktype)
        

    def get_mixer_freq(self, blockid, blocktype='dac'):
        try:
            return self.dict['freq'][blocktype][blockid]
        except KeyError:
            # Get tile and channel from id.
            tile, channel = [int(a) for a in blockid]

            # Fill freq dictionary.
            if blocktype == 'adc':
                self.dict['freq'][blocktype][blockid] = self.adc_tiles[tile].blocks[channel].MixerSettings['Freq']
            elif blocktype == 'dac':
                self.dict['freq'][blocktype][blockid] = self.dac_tiles[tile].blocks[channel].MixerSettings['Freq']
            else:
                raise RuntimeError("Blocktype %s not recognized" & blocktype)

            return self.dict['freq'][blocktype][blockid]

    def set_nyquist(self, blockid, nqz, blocktype='dac', force=False):
        # Check valid selection.
        if nqz not in [1,2]:
            raise RuntimeError("Nyquist zone must be 1 or 2")

        # Get tile and channel from id.
        tile, channel = [int(a) for a in blockid]

        # Need to update?
        if not force and self.get_nyquist(blockid,blocktype) == nqz:
            return

        if blocktype == 'adc':
            self.adc_tiles[tile].blocks[channel].NyquistZone = nqz
            self.dict['nqz'][blocktype][blockid] = nqz
        elif blocktype == 'dac':
            self.dac_tiles[tile].blocks[channel].NyquistZone = nqz
            self.dict['nqz'][blocktype][blockid] = nqz
        else:
            raise RuntimeError("Blocktype %s not recognized" & blocktype)

    def get_nyquist(self, blockid, blocktype='dac'):
        try:
            return self.dict['nqz'][blocktype][blockid]
        except KeyError:
            # Get tile and channel from id.
            tile, channel = [int(a) for a in blockid]

            # Fill nqz dictionary.
            if blocktype == 'adc':
                self.dict['nqz'][blocktype][blockid] = self.adc_tiles[tile].blocks[channel].NyquistZone
            elif blocktype == 'dac':
                self.dict['nqz'][blocktype][blockid] = self.dac_tiles[tile].blocks[channel].NyquistZone
            else:
                raise RuntimeError("Blocktype %s not recognized" & blocktype)

            return self.dict['nqz'][blocktype][blockid]

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
        if isinstance(soc, MkidsSoc) == False:
            raise RuntimeError("%s (MkidsSoc, AnalysisChain)" % __class__.__name__)
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

                # Does the chain has a chsel?
                if pfb.HAS_CHSEL:
                    self.maskall()

                # Does the chain has a streamer?
                if pfb.HAS_STREAMER:
                    # Default streamer samples.
                    streamer = getattr(self.soc, self.dict['chain']['streamer'])
                    streamer.set(10000)

                # Does the chain has a dds?
                if pfb.HAS_DDSCIC or pfb.HAS_DDS_DUAL:
                    # Frequency resolution (MHz).
                    dds = getattr(self.soc, self.dict['chain']['dds'])
                    self.dict['fr'] = dds.DF_DDS/1e6
                
                # Does the chain has a kidsim?
                elif pfb.HAS_KIDSIM:
                    # Frequency resolution (MHz).
                    kidsim = getattr(self.soc, self.dict['chain']['kidsim'])
                    self.dict['fr'] = kidsim.DF_DDS/1e6
 
    def update_settings(self):
        tile = int(self.dict['chain']['adc']['tile'])
        ch = int(self.dict['chain']['adc']['ch'])
        m_set = self.soc.rf.adc_tiles[tile].blocks[ch].MixerSettings
        self.dict['mixer'] = {
            'mode'     : self.return_key(self.mixer_dict['mode'], m_set['MixerMode']),
            'type'     : self.return_key(self.mixer_dict['type'], m_set['MixerType']),
            'evnt_src' : self.return_key(self.event_dict['source'], m_set['EventSource']),
            'freq'     : m_set['Freq'],
        }
        
        self.dict['nqz'] = self.soc.rf.adc_tiles[tile].blocks[ch].NyquistZone        
        
    def set_mixer_frequency(self, f):
        if self.dict['mixer']['type'] != 'fine':
            raise RuntimeError("Mixer not active")
        else:            
            # Set Mixer with RFDC driver.
            self.soc.rf.set_mixer_freq(self.dict['chain']['adc']['id'], f, 'adc')
            
            # Update local copy of frequency value.
            self.update_settings()
            
    def get_mixer_frequency(self):
        return self.soc.rf.get_mixer_freq(self.dict['chain']['adc']['id'],'adc')
        
    def return_key(self,dictionary,val):
        for key, value in dictionary.items():
            if value==val:
                return key
        return('Key Not Found')
    
    def source(self, source="product"):
        # Get dds block.
        dds_b = getattr(self.soc, self.dict['chain']['dds'])
        
        if dds_b is not None:
            # Set source.
            dds_b.dds_outsel(source)
    
    def set_decimation(self, value=2, autoq=True):
        """
        Sets the decimation value of the DDS+CIC or CIC block of the chain.
        
        :param value: desired decimation value.
        :type value: int
        :param autoq: flag for automatic quantization setting.
        :type autoq: boolean
        """
        # Get block.
        cic_b   = getattr(self.soc, self.dict['chain']['cic'])

        if cic_b is not None:
            if autoq:
                cic_b.decimation(value)
            else:
                cic_b.decimate(value)
    
    def unmask(self, ch=0, single=True, verbose=False):
        """
        Un-masks the specified channel of the Channel Selection block of the chain. When single=True, only one transaction
        will be activated. If single=False, channels will be unmasked without masking previously enabled channels.
        
        :param ch: channel number.
        :type ch: int
        :param single: flag for single transaction at a time.
        :type single: boolean
        """
        # Get chsel.
        chsel = getattr(self.soc, self.dict['chain']['chsel'])
                
        # Unmask channel.
        chsel.set(ch=ch, single=single, verbose=verbose)
        
    def maskall(self):
        """
        Mask all channels of the Channel Selection block of the chain.
        """
        # Get chsel.
        chsel = getattr(self.soc, self.dict['chain']['chsel'])
        
        # Mask all channels.
        chsel.alloff()
    
    def anyenabled(self):
        # Get chsel.
        chsel = getattr(self.soc, self.dict['chain']['chsel'])
        
        if len(chsel.enabled_channels) > 0:
            return True
        else:
            return False          

    def get_bin(self, f=0, g=0, force_dds=False, verbose=False):
        """
        Get data from the channels nearest to the specified frequency.
        Channel bandwidth depends on the selected chain options.
        
        :param f: specified frequency in MHz.
        :type f: float
        :param force_dds: flag for forcing programming dds_dual.
        :type force_dds: boolean
        :param verbose: flag for verbose output.
        :type verbose: boolean
        :return: [i,q] data from the channel.
        :rtype:[array,array]
        """
        # Get blocks.
        pfb_b = getattr(self.soc, self.dict['chain']['pfb'])
        dds_b = getattr(self.soc, self.dict['chain']['dds'])

        # Sanity check: is frequency on allowed range?
        fmix = abs(self.dict['mixer']['freq'])
        fs = self.dict['chain']['fs']
              
        if (fmix-fs/2) < f < (fmix+fs/2):
            f_ = f - fmix
            k = pfb_b.freq2ch(f_)
            
            # Compute resulting dds frequency.
            fdds = f_ - pfb_b.ch2freq(k)
            
            # Program dds frequency.
            if self.dict['chain']['subtype'] == 'single':
                dds_b.set_ddsfreq(ch_id=k, f=fdds*1e6)
            elif self.dict['chain']['subtype'] == 'dual' and force_dds:
                dds_b.ddscfg(f = fdds*1e6, g = g, ch = k)
                if verbose:
                    print("{}: force dds".format(__class__.__name__))

            if verbose:
                print("{}: f = {} MHz, fd = {} MHz, k = {}, fdds = {}".format(__class__.__name__, f, f_, k, fdds))
                
            return self.get_data(k,verbose)            
                
        else:
            raise ValueError("Frequency value %f out of allowed range [%f,%f]" % (f,fmix-fs/2,fmix+fs/2))

    def get_data(self, ch=0, verbose=False):
        # Get blocks.
        chsel_b    = getattr(self.soc, self.dict['chain']['chsel'])
        streamer_b = getattr(self.soc, self.dict['chain']['streamer'])
        
        # Unmask channel.
        self.unmask(ch, verbose=verbose)
        
        return streamer_b.get_data(nt=1, idx = chsel_b.ch2idx(ch))
    
    def get_data_all(self, verbose=False):
        """
        Get the data from all the enabled channels.
        """
        # Get blocks.        
        streamer_b = getattr(self.soc, self.dict['chain']['streamer'])
        
        # Check if any channel is enabled.
        if self.anyenabled():
            if verbose:
                print("{}: Some channels are enabled. Retrieving data...".format(__class__.__name__))
            
            return streamer_b.get_data_all(verbose=verbose)

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
    def decimation(self):
        cic_b   = getattr(self.soc, self.dict['chain']['cic'])

        if cic_b is not None:
            return cic_b.get_decimate()
        else:
            return 1
    
    @property
    def name(self):
        return self.dict['chain']['name']
    
    @property
    def dds(self):
        return getattr(self.soc, self.dict['chain']['ddscic'])    
        
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
        if isinstance(soc, MkidsSoc) == False:
            raise RuntimeError("%s (MkidsSoc, SynthesisChain)" % __class__.__name__)
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

                # Is this a PFB or Signal Generator-based chain?
                if 'pfb' in chain.keys():
                    self.dict['type'] = 'pfb'

                    # pfb block.
                    pfb = getattr(self.soc, self.dict['chain']['pfb'])

                    # Does this chain has a dds?
                    if pfb.HAS_DDS or pfb.HAS_DDS_DUAL:
                        # Set frequency resolution (MHz).
                        ddscic = getattr(self.soc, self.dict['chain']['dds'])
                        self.dict['fr'] = ddscic.DF_DDS/1e6

                    # Does this chain has a kidsim?
                    elif pfb.HAS_KIDSIM:
                        # Set frequency resolution (MHz).
                        kidsim = getattr(self.soc, self.dict['chain']['kidsim'])
                        self.dict['fr'] = kidsim.DF_DDS/1e6
                elif 'gen' in chain.keys():
                    self.dict['type'] = 'gen'

                    # Set frequency resolution.
                    ctrl = getattr(self.soc, self.dict['chain']['ctrl'])
                    self.dict['fr'] = ctrl.dict['df']
                else:
                    raise RuntimeError("Chain must have a PFB or Signal Generator")

                # Update settings.
                self.update_settings()

                # Disable all output tones.
                self.alloff()

                # Variable to keep track of active channel (pfb-based).
                self.enabled_ch = None
 
    def update_settings(self):
        tile = int(self.dict['chain']['dac']['tile'])
        ch = int(self.dict['chain']['dac']['ch'])
        m_set = self.soc.rf.dac_tiles[tile].blocks[ch].MixerSettings
        self.dict['mixer'] = {
            'mode'     : self.return_key(self.mixer_dict['mode'], m_set['MixerMode']),
            'type'     : self.return_key(self.mixer_dict['type'], m_set['MixerType']),
            'evnt_src' : self.return_key(self.event_dict['source'], m_set['EventSource']),
            'freq'     : m_set['Freq'],
        }
        
        self.dict['nqz'] = self.soc.rf.dac_tiles[tile].blocks[ch].NyquistZone        
        
    def set_mixer_frequency(self, f):
        if self.dict['mixer']['type'] != 'fine':
            raise RuntimeError("Mixer not active")
        else:            
            # Set Mixer with RFDC driver.
            self.soc.rf.set_mixer_freq(self.dict['chain']['dac']['id'], f, 'dac')
            
            # Update local copy of frequency value.
            self.update_settings()
            
    def get_mixer_frequency(self):
        return self.soc.rf.get_mixer_freq(self.dict['chain']['dac']['id'],'dac')
        
    def return_key(self,dictionary,val):
        for key, value in dictionary.items():
            if value==val:
                return key
        return('Key Not Found')
    
    # Set all DDS channels off.
    def alloff(self):
        if self.dict['type'] == 'pfb':
            # pfb block.
            pfb = getattr(self.soc, self.dict['chain']['pfb'])

            # Does this chain has a dds?
            if pfb.HAS_DDS or pfb.HAS_DDS_DUAL:
                dds = getattr(self.soc, self.dict['chain']['dds'])
                dds.alloff()
        else:
            ctrl = getattr(self.soc, self.dict['chain']['ctrl'])
            ctrl.set(g=0)

    # Set single output.
    def set_tone(self, f=0, g=0.99, cg=0, comp=False, verbose=False):
        # Sanity check: is frequency on allowed range?
        fmix = self.dict['mixer']['freq']
        fs = self.dict['chain']['fs']   
                
        if (fmix-fs/2) < f < (fmix+fs/2):
            f_ = f - fmix


            if self.dict['type'] == 'pfb':
                pfb_b = getattr(self.soc, self.dict['chain']['pfb'])
                dds_b = getattr(self.soc, self.dict['chain']['dds'])
                k = pfb_b.freq2ch(f_)
            
                # Compute resulting dds frequency.
                fdds = f_ - pfb_b.ch2freq(k)

                # Do I need to disable previous channel?
                if self.enabled_ch is not None:

                    # Channel is already active.
                    if self.enabled_ch == k:
                        if verbose:
                            print("{}: channel {} is active".format(__class__.__name__, k))  

                        # Program dds frequency.
                        dds_b.ddscfg(f = fdds*1e6, g = g, cg = cg, ch = k, comp = comp)

                        if verbose:
                            print("{}: f = {} MHz, fd = {} Mhz, k = {}, fdds = {} MHz".format(__class__.__name__, f, f_, k, fdds))

                    # Channel is not active yet.
                    else:
                        if verbose:
                            print("{}: channel {} is not active".format(__class__.__name__, k))  
                            print("{}: de-activate channel {} and activate channel {}".format(__class__.__name__, self.enabled_ch, k))  

                        # Disable active channel first.
                        dds_b.ddscfg(ch = self.enabled_ch)

                        # Program dds frequency.
                        dds_b.ddscfg(f = fdds*1e6, g = g, cg = cg, ch = k, comp = comp)

                        # Update active channel.
                        self.enabled_ch = k

                # First use. No channel is active.
                else:
                    if verbose:
                        print("{}: activate channel {}".format(__class__.__name__, k))  

                    # Program dds frequency.
                    dds_b.ddscfg(f = fdds*1e6, g = g, cg = cg, ch = k, comp = comp)

                    # Update active channel.
                    self.enabled_ch = k

            elif self.dict['type'] == 'gen':
                ctrl = getattr(self.soc, self.dict['chain']['ctrl'])
                ctrl.set(f = f_, g = g)

                if verbose:
                    print("{}: f = {} MHz, fd = {} Mhz".format(__class__.__name__, f, f_))
            
            else:
                raise RuntimeError("{}: not a recognized chain.".format(__class__.__name__))
            
        else:
            raise ValueError("Frequency value %f out of allowed range [%f,%f]" %(f, fmix-fs/2, fmix+fs/2))          

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
        if self.dict['type'] == 'pfb':
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
    
    @property
    def dds(self):
        return getattr(self.soc, self.dict['chain']['dds'])
    
class KidsChain():
    # Constructor.
    def __init__(self, soc, analysis=None, synthesis=None, dual=None, name=""):
        # Sanity check. Is soc the right type?
        if isinstance(soc, MkidsSoc) == False:
            raise RuntimeError("%s (MkidsSoc, Analysischain, SynthesisChain)" % __class__.__name__)
        else:
            # Soc instance.
            self.soc = soc
            
            # Chain name.
            self.name = name

            # Force dds flag.
            self.force_dds = False

            # Check Chains.
            if analysis is None and synthesis is None:
                # Must be a dual chain.
                if dual is None:
                    raise RuntimeError("%s Invalid Chains Provided. Options are Analysis,Synthesis or Dual" % __class__.name__)
                else:
                    # Dual Chain flag.
                    self.IS_DUAL = True

                    self.analysis   = AnalysisChain(self.soc, dual['analysis'])
                    self.synthesis  = SynthesisChain(self.soc, dual['synthesis'])

                    # Frequency resolution should be the same!!
                    if self.analysis.fr != self.synthesis.fr:
                        raise RuntimeError("%s Analysis and Syhtiesis Chains of provided Dual Chain are not equal." %__class__.__name)

                    self.fr = self.analysis.fr

            else:
                if analysis is not None and synthesis is None:
                    raise RuntimeError("%s Synthesis Chain Missing" % __class__.name__)
                if analysis is None and syntheis is not None:
                    raise RuntimeError("%s Analysis Chain Missing" % __class__.name__)
                    
                # Dual Chain flag.
                self.IS_DUAL = False

                # Analysis chain.
                self.analysis = AnalysisChain(self.soc, analysis)
                
                # Synthesis chain.
                self.synthesis = SynthesisChain(self.soc, synthesis)

                # Flag to force dds programming.
                # If a dual analysis chain is used with a gen-based synthesis, I need to force
                # the configuration of the DDS (given that it is not programmed at generation).
                if self.analysis.dict['chain']['subtype'] == 'dual' and self.synthesis.dict['type'] == 'gen':
                    self.force_dds = True
                
                # Frequency resolution.
                fr_min = min(self.analysis.fr,self.synthesis.fr)
                fr_max = max(self.synthesis.fr,self.synthesis.fr)
                self.fr = fr_max
                
                # Check Integer Ratio.
                div=fr_max/fr_min
                div_i=int(div)
                if div != div_i:
                    print("{} WARNING: analysis/syhtnesis frequency resolutions are not Integer.".format(__class__.__name__))
                
    def fq(self, f):
        return int(np.round(f/self.fr))*self.fr

    def set_mixer_frequency(self, f):
        self.analysis.set_mixer_frequency(-f) # -fmix to get upper sideband and avoid mirroring.
        self.synthesis.set_mixer_frequency(f)

    def set_tone(self, f=0, g=0.5, cg=0, comp=False, verbose=False):
        # Set tone using synthesis chain.
        self.synthesis.set_tone(f=f, g=g, cg=cg, comp=comp, verbose=verbose)
    
    def source(self, source="product"):
        # Set source using analysis chain.
        self.analysis.source(source = source)

    def set_decimation(self, value = 2, autoq = True):
        # Set decimation using analysis chain.
        self.analysis.set_decimation(value = value, autoq = autoq)

    def get_bin(self, f=0, verbose=False):
        # Get data from bin using analysis chain.
        return self.analysis.get_bin(f=f, force_dds = self.force_dds, verbose=verbose)
    
    def sweep(self, fstart, fend, N=10, g=0.5, decimation = 2, set_mixer=True, verbose=False):
        if set_mixer:
            # Set fmixer at the center of the sweep.
            fmix = (fstart + fend)/2
            fmix = self.fq(fmix)
            self.set_mixer_frequency(fmix)

        # Default settings.
        self.analysis.set_decimation(decimation)
        self.analysis.source("product")
        
        f_v = np.linspace(fstart,fend,N)

        # Check frequency resolution.
        fr = f_v[1] - f_v[0]
        if fr < self.fr:
            print("Required resolution too small. Redefining frequency vector with a resolution of {} MHz".format(self.fr))
            f_v = np.arange(self.fq(fstart), self.fq(fend), self.fr)
            N = len(f_v)
        
        fq_v = np.zeros(N)
        a_v = np.zeros(N)
        phi_v = np.zeros(N)
        i_v = np.zeros(N)
        q_v = np.zeros(N)
        
        print("Starting sweep:")
        print("  * Start      : {} MHz".format(fstart))
        print("  * End        : {} MHz".format(fend))
        print("  * Resolution : {} MHz".format(f_v[1]-f_v[0]))
        print("  * Points     : {}".format(N))
        print(" ")
        for i,f in enumerate(f_v):
            # Quantize frequency.
            fq = self.fq(f)
            
            # Set output tone.
            self.set_tone(f=fq, g=g, verbose=verbose)
            
            # Get input data.
            [xi,xq] = self.get_bin(fq, verbose=verbose)
          
            i0 = 100
            i1 = -100
            iMean = xi[i0:i1].mean()
            qMean = xq[i0:i1].mean()
            
            # Amplitude and phase.
            a = np.abs(iMean + 1j*qMean)
            phi = np.angle(iMean + 1j*qMean)

            fq_v[i] = fq
            a_v[i] = a
            phi_v[i] = phi
            
            if verbose:
                print("i = {}, f = {} MHz, fq = {} MHz, a = {}, phi = {}".format(i,f,fq,a,phi))
            else:
                print("{}".format(i), end=", ")
         
        return fq_v,a_v,phi_v

    def phase_slope(self, f, phi):
        # Compute phase jumps.
        dphi = np.diff(phi)
        idx  = np.argwhere(abs(dphi) > 0.9*2*np.pi).reshape(-1)
        
        # Compute df/dt.
        df = np.diff(f[idx]).mean()
        dt = 1/df

        return df, dt

    def phase_correction(self, f, phi, DT = 20, phase_cal = 0):
        # Unwrap phase.
        phi_u = np.unwrap(phi)
        phi_u = phi_u - phi_u[0]

        # Phase correction by delay DT.
        # phi_u = 2*pi*f*(DT + dt)
        # phi_u = 2*pi*f*DT + 2*pi*f*dt = phi_DT + phi_dt
        # phi_dt = phi_u - 2*pi*f*DT
        phi_dt = phi_u - 2*np.pi*f*DT
        phi_dt = phi_dt - phi_dt[0]

        # Phase-jump correction.
        k = np.zeros(len(f))
        for i in range(len(f)):
            k[i] = self.synthesis.freq2ch(f[i])

        # Apply jump compensation.
        phi_dt = phi_dt - phase_cal*(k - k[0])

        return phi_u, phi_dt

    def phase_fit(self, f, phi, jumps=True, gap=5):
        # Dictionary for output data.
        data = {}
        data['fits'] = []
        
        # Delay estimation using phase jumps.
        if jumps:
            # Phase diff.
            phi_diff = np.diff(phi)
            
            # Find jumps.
            jv = 0.8*np.max(np.abs(phi_diff))                
            idx = np.argwhere(np.abs(phi_diff) > jv).reshape(-1)
            data['jump'] = {'threshold' : jv, 'index' : idx, 'value' : phi_diff[idx]}
            
            idx_start = 0
            idx_end = len(f)
            for i in range(len(idx)):
                idx_end = idx[i]
                
                # Move away from midpoint.
                idx_start = idx_start + gap
                idx_end = idx_end - gap
                
                x = f[idx_start:idx_end]
                y = phi[idx_start:idx_end]
                coef = np.polyfit(x,y,1)
                fit_fn = np.poly1d(coef)
                
                fit_ = {'slope' : coef[0], 'data' : {'x' : x, 'y': y, 'fn' : fit_fn(x)}}
                data['fits'].append(fit_)
                
                # Update start index.
                idx_start = idx_end + gap
                
            # Section after last jump.
            idx_end = len(f)
    
            # Move away from midpoint.
            idx_start = idx_start + gap
            idx_end = idx_end - gap
    
            x = f[idx_start:idx_end]
            y = phi[idx_start:idx_end]
            coef = np.polyfit(x,y,1)
            fit_fn = np.poly1d(coef)
    
            fit_ = {'slope' : coef[0], 'data' : {'x' : x, 'y': y, 'fn' : fit_fn(x)}}
            data['fits'].append(fit_)        
            
            return data
        
        # Overall delay estimation.
        else:
            coef   = np.polyfit(f,phi, 1)
            fit_fn = np.poly1d(coef)
            
            fit_ = {'slope' : coef[0], 'data' : {'x' : f, 'y' : phi, 'fn' : fit_fn(f)}}
            data['fits'].append(fit_)
            
            return data

class SimuChain():
    # Constructor.
    def __init__(self, soc, simu=None, name=""):
        # Sanity check. Is soc the right type?
        if isinstance(soc, MkidsSoc) == False:
            raise RuntimeError("%s (MkidsSoc, SimuChain)" % __class__.__name__)
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

    def set_mixer_frequency(self, f):
        self.analysis.set_mixer_frequency(-f) # -fmix to get upper sideband and avoid mirroring.
        self.synthesis.set_mixer_frequency(f)

    def enable(self, f, verbose=False):
        # Config dictionary.
        cfg_ = {'sel' : 'resonator', 'freq' : f}
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
            
            # Compute DDS frequency.
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

class MkidsSoc(Overlay, QickConfig):    

    # Constructor.
    def __init__(self, bitfile=None, force_init_clks=False, ignore_version=True, clk_output=None, external_clk=None, **kwargs):
        """
        Constructor method
        """

        self.external_clk = external_clk
        self.clk_output = clk_output

        # Load bitstream.
        if bitfile is None:
            raise RuntimeError("bitfile name must be provided")
        else:
            Overlay.__init__(self, bitfile, ignore_version=ignore_version, download=False, **kwargs)
        
        # Initialize the configuration
        self._cfg = {}
        QickConfig.__init__(self)

        self['board'] = os.environ["BOARD"]

        # Read the config to get a list of enabled ADCs and DACs, and the sampling frequencies.
        self.list_rf_blocks(
            self.ip_dict['usp_rf_data_converter_0']['parameters'])

        self.config_clocks(force_init_clks)

        # RF data converter (for configuring ADCs and DACs, and setting NCOs)
        self.rf = self.usp_rf_data_converter_0
        self.rf.configure(self)

        # Extract the IP connectivity information from the HWH parser and metadata.
        self.metadata = QickMetadata(self)

        self.map_signal_paths()

    def description(self):
        """Generate a printable description of the QICK configuration.

        Parameters
        ----------

        Returns
        -------
        str
            description

        """
        lines = []
        lines.append("\n\tBoard: " + self['board'])

        lines.append("\n\tAnalysis Chains")
        for i, chain in enumerate(self['analysis']):
            name = ""
            if 'name' in chain.keys():
                name = ", " + chain['name']
            lines.append("\t%d:\t Analysis Chain: ADC Tile = %d, ADC Ch = %d, fs = %.3f MHz, Number of Channels = %d %s" %
                         (i, int(chain['adc']['tile']), int(chain['adc']['ch']), chain['fs'], chain['nch'], name))

        lines.append("\n\tSynthesis Chains")
        for i, chain in enumerate(self['synthesis']):
            name = ""
            if 'name' in chain.keys():
                name = ", " + chain['name']
            lines.append("\t%d:\t Synthesis Chain: DAC Tile = %d, DAC Ch = %d, fs = %.3f MHz, Number of Channels = %d %s" %
                         (i, int(chain['dac']['tile']), int(chain['dac']['ch']), chain['fs'], chain['nch'], name))

        # Dual Chains.
        if len(self['dual']) > 0:
            lines.append("\n\tDual Chains")
            for i, chain in enumerate(self['dual']):
                chain_a = chain['analysis']
                chain_s = chain['synthesis']
                name = ""
                if 'name' in chain.keys():
                    name = chain['name']
                lines.append("\tDual %d: %s" % (i,name))
                lines.append("\t\tAnalysis : ADC Tile = %d, ADC Ch = %d, fs = %.3f MHz, Number of Channels = %d" %
                            (int(chain_a['adc']['tile']), int(chain_a['adc']['ch']), chain_a['fs'], chain_a['nch']))
                lines.append("\t\tSynthesis: DAC Tile = %d, DAC Ch = %d, fs = %.3f MHz, Number of Channels = %d\n" %
                             (int(chain_s['dac']['tile']), int(chain_s['dac']['ch']), chain_s['fs'], chain_s['nch']))

        # Sim Chains.
        if len(self['simu']) > 0:
            lines.append("\n\tSim Chains")
            for i, chain in enumerate(self['simu']):
                chain_a = chain['analysis']
                chain_s = chain['synthesis']
                name = ""
                if 'name' in chain.keys():
                    name = chain['name']
                lines.append("\tSim %d: %s" % (i,name))
                lines.append("\t\tAnalysis : ADC Tile = %d, ADC Ch = %d, fs = %.3f MHz, Number of Channels = %d" %
                            (int(chain_a['adc']['tile']), int(chain_a['adc']['ch']), chain_a['fs'], chain_a['nch']))
                lines.append("\t\tSynthesis: DAC Tile = %d, DAC Ch = %d, fs = %.3f MHz, Number of Channels = %d\n" %
                             (int(chain_s['dac']['tile']), int(chain_s['dac']['ch']), chain_s['fs'], chain_s['nch']))


        lines.append("\n\t%d ADCs:" % (len(self['adcs'])))
        for adc in self['adcs']:
            tile, block = [int(c) for c in adc]
            fs = self.adcs[adc]['fs']
            decimation = self.adcs[adc]['decimation']
            if self['board']=='ZCU111':
                label = "ADC%d_T%d_CH%d" % (tile + 224, tile, block)
            elif self['board']=='ZCU216':
                label = "%d_%d, on JHC%d" % (block, tile + 224, 5 + (block%2) + 2*(tile//2))
            elif self['board']=='ZCU208':
                label = "%d_%d, on JHC%d" % (block, tile + 224, 5 + (block%2) + 2*(tile//2))
            elif self['board']=='RFSoC4x2':
                label = {'00': 'ADC_D', '01': 'ADC_C', '20': 'ADC_B', '21': 'ADC_A'}[adc]
            lines.append("\t\tADC tile %d, ch %d, fs = %.3f MHz, decimation = %d, %s" %
                         (tile, block, fs, decimation, label))

        lines.append("\n\t%d DACs:" % (len(self['dacs'])))
        for dac in self['dacs']:
            tile, block = [int(c) for c in dac]
            fs = self.dacs[dac]['fs']
            interpolation = self.dacs[dac]['interpolation']
            if self['board']=='ZCU111':
                label = "DAC%d_T%d_CH%d" % (tile + 228, tile, block)
            elif self['board']=='ZCU216':
                label = "%d_%d, on JHC%d" % (block, tile + 228, 1 + (block%2) + 2*(tile//2))
            elif self['board']=='ZCU208':
                label = "%d_%d, on JHC%d" % (block, tile + 228, 1 + (block%2) + 2*(tile//2))
            elif self['board']=='RFSoC4x2':
                label = {'00': 'DAC_B', '20': 'DAC_A'}[dac]
            lines.append("\t\tDAC tile %d, ch %d, fs = %.3f MHz, interpolation = %d, %s" %
                         (tile, block, fs, decimation, label))

        return "\nQICK configuration:\n"+"\n".join(lines)

    def map_signal_paths(self):
        # Use the HWH parser to trace connectivity and deduce the channel numbering.
        for key, val in self.ip_dict.items():
            if hasattr(val['driver'], 'configure_connections'):
                getattr(self, key).configure_connections(self)

        # PFB for Analysis.
        self.pfbs_in = []
        pfbs_in_drivers = set([AxisPfbAnalysis])

        # PFB for Synthesis.
        self.pfbs_out = []
        pfbs_out_drivers = set([AxisPfbSynthesis])

        # SG for Synthesis.
        # TODO: provide support for Signal Generator Based synthesis chains.
        self.gens = []
        gens_drivers = set()

        # Populate the lists with the registered IP blocks.
        for key, val in self.ip_dict.items():
            if val['driver'] in pfbs_in_drivers:
                self.pfbs_in.append(getattr(self, key))
            elif val['driver'] in pfbs_out_drivers:
                self.pfbs_out.append(getattr(self, key))
            elif val['driver'] in gens_drivers:
                self.gens.append(getattr(self, key))

        # Configure the drivers.
        for pfb in self.pfbs_in:
            adc = pfb.dict['adc']['id']
            pfb.configure(self.adcs[adc]['fs']/self.adcs[adc]['decimation'])

            # Does this pfb has a DDSCIC?
            if pfb.HAS_DDSCIC:
                block = getattr(self, pfb.dict['ddscic'])
                block.configure(pfb.dict['freq']['fb'])

            # Does this pfb has a KIDSIM?
            if pfb.HAS_KIDSIM:
                block = getattr(self, pfb.dict['kidsim'])
                block.configure(pfb.dict['freq']['fb'])

            # Does this pfb has a DDS_DUAL?
            if pfb.HAS_DDS_DUAL:
                block = getattr(self, pfb.dict['dds'])
                block.configure(pfb.dict['freq']['fb'])

            # Does this pfb has a CHSEL?
            #if pfb.HAS_CHSEL:
            #    block = getattr(self, pfb.dict['chsel'])

            # Does this pfb has a STREAMER?
            if pfb.HAS_STREAMER:
                # Does this pfb has a DMA?
                if pfb.HAS_DMA:
                    dma     = getattr(self, pfb.dict['dma']) 
                    block   = getattr(self, pfb.dict['streamer'])
                    block.configure(dma)
                else:
                    raise RuntimeError("Block {} has a streamer but not a DMA." % pfb)

        for pfb in self.pfbs_out:
            dac = pfb.dict['dac']['id']
            pfb.configure(self.dacs[dac]['fs']/self.dacs[dac]['interpolation'])

            # Does this pfb has a DDSCIC?
            if pfb.HAS_DDS:
                block = getattr(self, pfb.dict['dds'])
                block.configure(pfb.dict['freq']['fb'])

        for gen in self.gens:
            dac = gen.dict['dac']['id']
            gen.configure(self.dacs[dac]['fs']/self.dacs[dac]['interpolation'])
            
            # Does this block has a CTRL?
            if gen.HAS_CTRL:
                block = getattr(self, gen.dict['ctrl'])
                block.configure(gen)

        self['adcs'] = list(self.adcs.keys())
        self['dacs'] = list(self.dacs.keys())
        self['analysis'] = []
        self['synthesis'] = []
        self['dual'] = []
        self['simu'] = []
        for pfb in self.pfbs_in:
            thiscfg = {}
            thiscfg['type'] = 'analysis'
            thiscfg['adc'] = pfb.dict['adc']
            thiscfg['pfb'] = pfb.fullpath
            if pfb.HAS_DDSCIC:
                thiscfg['subtype'] = 'single'
                thiscfg['dds'] = pfb.dict['ddscic']
                thiscfg['cic'] = pfb.dict['ddscic']
            elif pfb.HAS_DDS_DUAL:
                thiscfg['subtype'] = 'dual'
                thiscfg['dds'] = pfb.dict['dds']
                if pfb.HAS_CIC:
                    thiscfg['cic'] = pfb.dict['cic']
                else:
                    thiscfg['cic'] = None
            elif pfb.HAS_KIDSIM:
                thiscfg['subtype'] = 'sim'
                thiscfg['kidsim'] = pfb.dict['kidsim']
            if pfb.HAS_CHSEL:
                thiscfg['chsel'] = pfb.dict['chsel']
            if pfb.HAS_STREAMER:
                thiscfg['streamer'] = pfb.dict['streamer']
            if pfb.HAS_DMA:
                thiscfg['dma'] = pfb.dict['dma']
            thiscfg['fs'] = pfb.dict['freq']['fs']
            thiscfg['fs_ch'] = pfb.dict['freq']['fb']
            thiscfg['fc_ch'] = pfb.dict['freq']['fc']
            thiscfg['nch'] = pfb.dict['N']
            self['analysis'].append(thiscfg)

        for pfb in self.pfbs_out:
            thiscfg = {}
            thiscfg['type'] = 'synthesis'
            if pfb.HAS_DDS:
                thiscfg['subtype'] = 'single'
                thiscfg['dds'] = pfb.dict['dds']
            elif pfb.HAS_DDS_DUAL:
                thiscfg['subtype'] = 'dual'
                thiscfg['dds'] = pfb.dict['dds']
            elif pfb.HAS_KIDSIM:
                thiscfg['subtype'] = 'sim'
                thiscfg['kidsim'] = pfb.dict['kidsim']
            thiscfg['dac'] = pfb.dict['dac']
            thiscfg['pfb'] = pfb.fullpath
            thiscfg['fs'] = pfb.dict['freq']['fs']
            thiscfg['fs_ch'] = pfb.dict['freq']['fb']
            thiscfg['fc_ch'] = pfb.dict['freq']['fc']
            thiscfg['nch'] = pfb.dict['N']
            self['synthesis'].append(thiscfg)

        for gen in self.gens:
            thiscfg = {}
            thiscfg['type'] = 'synthesis'
            thiscfg['subtype'] = 'single'
            thiscfg['dac'] = gen.dict['dac']
            thiscfg['gen'] = gen.fullpath
            thiscfg['ctrl'] = gen.dict['ctrl']
            thiscfg['fs'] = gen.dict['freq']['fs']
            thiscfg['nch'] = 1
            self['synthesis'].append(thiscfg)

        # Search for dual/simulation chains.
        for ch_a in self['analysis']:
            # Is it dual?
            if ch_a['subtype'] == 'dual':
                # Find matching chain (they share a axis_dds_dual block).
                found = False
                dds = ch_a['dds']
                for ch_s in self['synthesis']:
                    # Is it dual?
                    if ch_s['subtype'] == 'dual':
                        if dds == ch_s['dds']:
                            found = True 
                            thiscfg = {}
                            thiscfg['analysis']  = ch_a
                            thiscfg['synthesis'] = ch_s
                            self['dual'].append(thiscfg)
                    
                # If not found print an error.
                if not found:
                    raise RuntimeError("Could not find dual chain for PFB {}".format(ch_a['pfb']))

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

    def config_clocks(self, force_init_clks):
        """
        Configure PLLs if requested, or if any ADC/DAC is not locked.
        """
              
        # if we're changing the clock config, we must set the clocks to apply the config
        if force_init_clks or (self.external_clk is not None) or (self.clk_output is not None):
            QickSoc.set_all_clks(self)
            self.download()
        else:
            self.download()
            if not QickSoc.clocks_locked(self):
                QickSoc.set_all_clks(self)
                self.download()
        if not QickSoc.clocks_locked(self):
            print(
                "Not all DAC and ADC PLLs are locked. You may want to repeat the initialization of the QickSoc.")

    def list_rf_blocks(self, rf_config):
        """
        Lists the enabled ADCs and DACs and get the sampling frequencies.
        XRFdc_CheckBlockEnabled in xrfdc_ap.c is not accessible from the Python interface to the XRFdc driver.
        This re-implements that functionality.
        """

        self.hs_adc = rf_config['C_High_Speed_ADC'] == '1'

        self.dac_tiles = []
        self.adc_tiles = []
        dac_fabric_freqs = []
        adc_fabric_freqs = []
        refclk_freqs = []
        self.dacs = {}
        self.adcs = {}

        for iTile in range(4):
            if rf_config['C_DAC%d_Enable' % (iTile)] != '1':
                continue
            self.dac_tiles.append(iTile)
            f_fabric = float(rf_config['C_DAC%d_Fabric_Freq' % (iTile)])
            f_refclk = float(rf_config['C_DAC%d_Refclk_Freq' % (iTile)])
            dac_fabric_freqs.append(f_fabric)
            refclk_freqs.append(f_refclk)
            fs = float(rf_config['C_DAC%d_Sampling_Rate' % (iTile)])*1000
            interpolation = int(rf_config['C_DAC%d_Interpolation' % (iTile)])
            for iBlock in range(4):
                if rf_config['C_DAC_Slice%d%d_Enable' % (iTile, iBlock)] != 'true':
                    continue
                self.dacs["%d%d" % (iTile, iBlock)] = {'fs': fs,
                                                       'f_fabric': f_fabric,
                                                       'interpolation' : interpolation}

        for iTile in range(4):
            if rf_config['C_ADC%d_Enable' % (iTile)] != '1':
                continue
            self.adc_tiles.append(iTile)
            f_fabric = float(rf_config['C_ADC%d_Fabric_Freq' % (iTile)])
            f_refclk = float(rf_config['C_ADC%d_Refclk_Freq' % (iTile)])
            adc_fabric_freqs.append(f_fabric)
            refclk_freqs.append(f_refclk)
            fs = float(rf_config['C_ADC%d_Sampling_Rate' % (iTile)])*1000
            decimation = int(rf_config['C_ADC%d_Decimation' % (iTile)])
            for iBlock in range(4):
                if self.hs_adc:
                    if iBlock >= 2 or rf_config['C_ADC_Slice%d%d_Enable' % (iTile, 2*iBlock)] != 'true':
                        continue
                else:
                    if rf_config['C_ADC_Slice%d%d_Enable' % (iTile, iBlock)] != 'true':
                        continue
                self.adcs["%d%d" % (iTile, iBlock)] = {'fs': fs,
                                                       'f_fabric': f_fabric,
                                                       'decimation' : decimation}

        def get_common_freq(freqs):
            """
            Check that all elements of the list are equal, and return the common value.
            """
            if not freqs:  # input is empty list
                return None
            if len(set(freqs)) != 1:
                raise RuntimeError("Unexpected frequencies:", freqs)
            return freqs[0]

        self['refclk_freq'] = get_common_freq(refclk_freqs)

