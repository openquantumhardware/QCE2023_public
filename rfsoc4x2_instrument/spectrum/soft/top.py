import os
from pynq.overlay import Overlay
import xrfclk
import xrfdc
import numpy as np

from drivers.ip import *
from drivers.pfb import *
from drivers.misc import *
from drivers.ip import SocIp, QickMetadata, QickConfig
from helpers import *


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

    # Coarse Mixer Dictionary.
    coarse_dict = {
        'off' : 0,
        'fs_div_2' : 2,
        'fs_div_4' : 4,
        'mfs_div_4' : 8,
        'bypass' : 16
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
        if isinstance(soc, TopSoc) == False:
            raise RuntimeError("%s (TopSoc, AnalysisChain)" % __class__.__name__)
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

    def update_settings(self):
        tile = int(self.dict['chain']['adc']['tile'])
        ch = int(self.dict['chain']['adc']['ch'])
        m_set = self.soc.rf.adc_tiles[tile].blocks[ch].MixerSettings
        self.dict['mixer'] = {
            'mode'     : self.return_key(self.mixer_dict['mode'], m_set['MixerMode']),
            'type'     : self.return_key(self.mixer_dict['type'], m_set['MixerType']),
            'evnt_src' : self.return_key(self.event_dict['source'], m_set['EventSource']),
        }

        # Check type.
        if self.dict['mixer']['type'] == 'fine':
            self.dict['mixer']['freq'] = m_set['Freq']
        elif self.dict['mixer']['type'] == 'coarse':
            type_c = self.return_key(self.coarse_dict, m_set['CoarseMixFreq'])
            fs_adc = self.soc.adcs[self.dict['chain']['adc']['id']]['fs']
            if type_c == 'fs_div_2':
                freq = fs_adc/2
            elif type_c == 'fs_div_4':
                freq = fs_adc/4
            elif type_c == 'mfs_div_4':
                freq = -fs_adc/4
            else:
                raise ValueError("Mixer CoarseMode %s not recognized" % (type_c))

            self.dict['mixer']['freq'] = freq
                
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
        return self.dict['mixer']['freq']
        
    def return_key(self,dictionary,val):
        for key, value in dictionary.items():
            if value==val:
                return key
        return('Key Not Found')
    
    def get_data_adc(self, verbose=False):
        # Get blocks.
        buff_b = getattr(self.soc, self.dict['chain']['buff_adc'])

        # Return data.
        return buff_b.get_data()

    def get_bin_pfb(self, f=0, verbose=False):
        """
        Get data from the channel nearest to the specified frequency.
        
        :param f: specified frequency in MHz.
        :type f: float
        :param verbose: flag for verbose output.
        :type verbose: boolean
        :return: [i,q] data from the channel.
        :rtype:[array,array]
        """
        # Get blocks.
        pfb_b   = getattr(self.soc, self.dict['chain']['pfb'])
        chsel_b = getattr(self.soc, pfb_b.dict['buff_pfb_chsel'])
        buff_b = getattr(self.soc, self.dict['chain']['buff_pfb'])

        # Sanity check: is frequency on allowed range?
        fmix = abs(self.dict['mixer']['freq'])
        fs = self.dict['chain']['fs']
              
        if (fmix-fs/2) < f < (fmix+fs/2):
            f_ = f - fmix
            k = pfb_b.freq2ch(f_)

            # Un-mask channel.
            chsel_b.set(k)
            
            if verbose:
                print("{}: f = {} MHz, fd = {} MHz, k = {}".format(__class__.__name__, f, f_, k))

            # Get data.
            return buff_b.get_data()
                
        else:
            raise ValueError("Frequency value %f out of allowed range [%f,%f]" % (f,fmix-fs/2,fmix+fs/2))

    def get_bin_xfft(self, f=0, verbose=False):
        """
        Get data from the channel nearest to the specified frequency.
        
        :param f: specified frequency in MHz.
        :type f: float
        :param verbose: flag for verbose output.
        :type verbose: boolean
        :return: [i,q] data from the channel.
        :rtype:[array,array]
        """
        # Get blocks.
        pfb_b   = getattr(self.soc, self.dict['chain']['pfb'])
        chsel_b = getattr(self.soc, pfb_b.dict['buff_xfft_chsel'])
        buff_b = getattr(self.soc, self.dict['chain']['buff_xfft'])

        # Sanity check: is frequency on allowed range?
        fmix = abs(self.dict['mixer']['freq'])
        fs = self.dict['chain']['fs']
              
        if (fmix-fs/2) < f < (fmix+fs/2):
            f_ = f - fmix
            k = pfb_b.freq2ch(f_)

            # Un-mask channel.
            chsel_b.set(k)
            
            if verbose:
                print("{}: f = {} MHz, fd = {} MHz, k = {}".format(__class__.__name__, f, f_, k))

            # Get data.
            [xi,xq,idx] = buff_b.get_data()
            x = xi + 1j*xq
            x = sort_br(x,idx)
            return x.real,x.imag
                
        else:
            raise ValueError("Frequency value %f out of allowed range [%f,%f]" % (f,fmix-fs/2,fmix+fs/2))

    def get_data_acc(self, N=1, verbose=False):
        # Get blocks.
        acc_b = getattr(self.soc, self.dict['chain']['accumulator'])
        x = acc_b.single_shot(N=N)
        x = np.roll(x, -int(self.soc.FFT_N/4))
        return x
    
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
        return self.dict['chain']['fs_ch']

    @property
    def nch(self):
        return self.dict['chain']['nch']

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
        if isinstance(soc, TopSoc) == False:
            raise RuntimeError("%s (TopSoc, SynthesisChain)" % __class__.__name__)
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

                # Update settings.
                self.update_settings()

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
    
    # Set single output.
    def set_tone(self, f=0, g=0.99, verbose=False):
        # Get blocks.
        iq_b = getattr(self.soc, self.dict['chain']['iq'])

        # Set mixer frequency.
        self.set_mixer_frequency(f)

        # Set IQ constant amplitude.
        iq_b.set_iq(i=g, q=g)            
        
class DualChain():
    # Constructor.
    def __init__(self, soc, analysis, synthesis):
        # Sanity check. Is soc the right type?
        if isinstance(soc, TopSoc) == False:
            raise RuntimeError("%s (TopSoc, Analysischain, SynthesisChain)" % __class__.__name__)
        else:
            # Soc instance.
            self.soc = soc

            # Analsis and Synthesis chains.
            self.analysis   = AnalysisChain(self.soc, analysis)
            self.synthesis  = SynthesisChain(self.soc, synthesis)
            
    def set_tone(self, f=0, g=0.5, verbose=False):
        # Set tone using synthesis chain.
        self.synthesis.set_tone(f=f, g=g, verbose=verbose)

    def get_data_adc(self, verbose=False):
        return self.analysis.get_data_adc(verbose=verbose)

    def get_bin_pfb(self, f=0, verbose=False):
        return self.analysis.get_bin_pfb(f=f, verbose=verbose)

    def get_bin_xfft(self, f=0, verbose=False):
        return self.analysis.get_bin_xfft(f=f, verbose=verbose)

    def get_data_acc(self, N=1, verbose=False):
        return self.analysis.get_data_acc(N=N, verbose=verbose)

    @property
    def fs(self):
        return self.analysis.fs
    
    @property
    def fc_ch(self):
        return self.analysis.fc_ch
    
    @property
    def fs_ch(self):
        return self.analysis.fs_ch

    @property
    def nch(self):
        return self.analysis.nch

class TopSoc(Overlay, QickConfig):    

    # Constructor.
    def __init__(self, bitfile, force_init_clks=False, ignore_version=True, **kwargs):
        """
        Constructor method
        """

        self.external_clk = False
        self.clk_output = False

        # Load bitstream.
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

        # Add XFFT order manually.
        self.FFT_N = 32768

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

        # Analysis Chains.
        if len(self['analysis']) > 0:
            for i, chain in enumerate(self['analysis']):
                adc_ = self.adcs[chain['adc']['id']]
                lines.append("\tAnalysis %d:" % (i))
                lines.append("\t\tADC: %d_%d, fs = %.1f MHz, Decimation    = %d" %
                            (224+int(chain['adc']['tile']), int(chain['adc']['ch']), adc_['fs'], adc_['decimation']))
                lines.append("\t\tPFB: fs = %.1f MHz, fc = %.1f MHz, %d channels" %
                            (chain['fs_ch'], chain['fc_ch'], chain['nch']))
                #lines.append("\t\tXFFT
        return "\nBREAD configuration:\n"+"\n".join(lines)

    def map_signal_paths(self):
        # Use the HWH parser to trace connectivity and deduce the channel numbering.
        for key, val in self.ip_dict.items():
            if hasattr(val['driver'], 'configure_connections'):
                getattr(self, key).configure_connections(self)

        # PFB for Analysis.
        self.pfbs_in = []
        pfbs_in_drivers = set([AxisPfbAnalysis])

        # IQ Constants.
        self.iqs = []
        iqs_drivers = set([AxisConstantIQ])

        # Populate the lists with the registered IP blocks.
        for key, val in self.ip_dict.items():
            if val['driver'] in pfbs_in_drivers:
                self.pfbs_in.append(getattr(self, key))
            elif val['driver'] in iqs_drivers:
                self.iqs.append(getattr(self, key))

        # Configure the drivers.
        for pfb in self.pfbs_in:
            adc = pfb.dict['adc']['id']

            # PFB.
            pfb.configure(self.adcs[adc]['fs']/self.adcs[adc]['decimation'])

            # BUFF_ADC: mr_buffer_et.
            if pfb.HAS_BUFF_ADC:
                block = getattr(self, pfb.dict['buff_adc'])
                dma = getattr(self, pfb.dict['buff_adc_dma'])
                block.configure(dma)

            # BUFF_PFB: axis_buffer_v1.
            if pfb.HAS_BUFF_PFB:
                block = getattr(self, pfb.dict['buff_pfb'])
                dma = getattr(self, pfb.dict['buff_pfb_dma'])
                block.configure(dma)

            # BUFF_XFFT: axis_buffer_uram.
            if pfb.HAS_BUFF_XFFT:
                block = getattr(self, pfb.dict['buff_xfft'])
                dma = getattr(self, pfb.dict['buff_xfft_dma'])
                block.configure(dma, sync="yes")

            # ACCUMULATOR: axis_accumulator_v1.
            if pfb.HAS_ACCUMULATOR:
                block = getattr(self, pfb.dict['accumulator'])
                dma = getattr(self, pfb.dict['dma'])
                block.configure(dma)

        self['adcs'] = list(self.adcs.keys())
        self['dacs'] = list(self.dacs.keys())
        self['analysis'] = []
        self['synthesis'] = []
        for pfb in self.pfbs_in:
            thiscfg = {}
            thiscfg['type']     = 'analysis'
            thiscfg['pfb']      = pfb.fullpath
            thiscfg['fs']       = pfb.dict['freq']['fs']
            thiscfg['fs_ch']    = pfb.dict['freq']['fb']
            thiscfg['fc_ch']    = pfb.dict['freq']['fc']
            thiscfg['nch']      = pfb.dict['N']
            if pfb.HAS_ADC:
                thiscfg['adc'] = pfb.dict['adc']
            if pfb.HAS_XFFT:
                thiscfg['xfft'] = pfb.dict['xfft']
            if pfb.HAS_ACCUMULATOR:
                thiscfg['accumulator'] = pfb.dict['accumulator']
            if pfb.HAS_BUFF_ADC:
                thiscfg['buff_adc'] = pfb.dict['buff_adc']
            if pfb.HAS_BUFF_PFB:
                thiscfg['buff_pfb'] = pfb.dict['buff_pfb']
            if pfb.HAS_BUFF_XFFT:
                thiscfg['buff_xfft'] = pfb.dict['buff_xfft']
                
            self['analysis'].append(thiscfg)

        # IQ Constant based synthesis.
        for iq in self.iqs:
            thiscfg = {}
            thiscfg['type']     = 'synthesis'
            thiscfg['iq'] = iq.fullpath
            thiscfg['dac'] = iq.dict['dac']

            self['synthesis'].append(thiscfg)

    def config_clocks(self, force_init_clks):
        """
        Configure PLLs if requested, or if any ADC/DAC is not locked.
        """
              
        # if we're changing the clock config, we must set the clocks to apply the config
        if force_init_clks:
            self.set_all_clks()
            self.download()
        else:
            self.download()
            if not self.clocks_locked():
                self.set_all_clks()
                self.download()
        if not self.clocks_locked():
            print(
                "Not all DAC and ADC PLLs are locked. You may want to repeat the initialization of the QickSoc.")

    def set_all_clks(self):
        """
        Resets all the board clocks
        """
        if self['board'] == 'ZCU111':
            # master clock generator is LMK04208, always outputs 122.88
            # DAC/ADC are clocked by LMX2594
            # available: 102.4, 204.8, 409.6, 737.0
            lmk_freq = 122.88
            lmx_freq = self['refclk_freq']
            print("resetting clocks:", lmk_freq, lmx_freq)

            if hasattr(xrfclk, "xrfclk"): # pynq 2.7
                # load the default clock chip configurations from file, so we can then modify them
                xrfclk.xrfclk._find_devices()
                xrfclk.xrfclk._read_tics_output()
                if self.clk_output:
                    # change the register for the LMK04208 chip's 5th output, which goes to J108
                    # we need this for driving the RF board
                    xrfclk.xrfclk._Config['lmk04208'][lmk_freq][6] = 0x00140325
                if self.external_clk:
                    # default value is 0x2302886D
                    xrfclk.xrfclk._Config['lmk04208'][lmk_freq][14] = 0x2302826D
            else: # pynq 2.6
                if self.clk_output:
                    # change the register for the LMK04208 chip's 5th output, which goes to J108
                    # we need this for driving the RF board
                    xrfclk._lmk04208Config[lmk_freq][6] = 0x00140325
                else: # restore the default
                    xrfclk._lmk04208Config[lmk_freq][6] = 0x80141E05
                if self.external_clk:
                    xrfclk._lmk04208Config[lmk_freq][14] = 0x2302826D
                else: # restore the default
                    xrfclk._lmk04208Config[lmk_freq][14] = 0x2302886D
            xrfclk.set_all_ref_clks(lmx_freq)
        elif self['board'] == 'ZCU216':
            # master clock generator is LMK04828, which is used for DAC/ADC clocks
            # only 245.76 available by default
            # LMX2594 is not used
            # available: 102.4, 204.8, 409.6, 491.52, 737.0
            lmk_freq = self['refclk_freq']
            lmx_freq = self['refclk_freq']*2
            print("resetting clocks:", lmk_freq, lmx_freq)

            assert hasattr(xrfclk, "xrfclk") # ZCU216 only has a pynq 2.7 image
            xrfclk.xrfclk._find_devices()
            xrfclk.xrfclk._read_tics_output()
            if self.external_clk:
                # default value is 0x01471A
                xrfclk.xrfclk._Config['lmk04828'][lmk_freq][80] = 0x01470A
            if self.clk_output:
                # default value is 0x012C22
                xrfclk.xrfclk._Config['lmk04828'][lmk_freq][55] = 0x012C02
            xrfclk.set_ref_clks(lmk_freq=lmk_freq, lmx_freq=lmx_freq)
        elif self['board'] == 'RFSoC4x2':
            # master clock generator is LMK04828, always outputs 245.76
            # DAC/ADC are clocked by LMX2594
            # available: 102.4, 204.8, 409.6, 491.52, 737.0
            lmk_freq = 245.76
            lmx_freq = self['refclk_freq']
            print("resetting clocks:", lmk_freq, lmx_freq)

            xrfclk.xrfclk._find_devices()
            xrfclk.xrfclk._read_tics_output()
            if self.external_clk:
                # default value is 0x01471A
                xrfclk.xrfclk._Config['lmk04828'][lmk_freq][80] = 0x01470A
            xrfclk.set_ref_clks(lmk_freq=lmk_freq, lmx_freq=lmx_freq)

    def clocks_locked(self):
        """
        Checks whether the DAC and ADC PLLs are locked.
        This can only be run after the bitstream has been downloaded.

        :return: clock status
        :rtype: bool
        """

        dac_locked = [self.usp_rf_data_converter_0.dac_tiles[iTile]
                      .PLLLockStatus == 2 for iTile in self.dac_tiles]
        adc_locked = [self.usp_rf_data_converter_0.adc_tiles[iTile]
                      .PLLLockStatus == 2 for iTile in self.adc_tiles]
        return all(dac_locked) and all(adc_locked)

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

