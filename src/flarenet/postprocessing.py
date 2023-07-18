import numpy as np
import lightkurve as lk
import pandas as pd
from sklearn.preprocessing import RobustScaler

from flare_model import * 
from cosmic_ray_extension import *

all = ['InputTPF', 'TESSTargetPixelFile']

class InputTPF(lk.TessTargetPixelFile):
    """
    Contains all the functions to search for & download a lightkurve TargetPixelFile, 
    extract time series and meta data for input into our model, ...
    """

    @staticmethod
    def download_tpf(ticid, sector, exptime, download_dir):
        x = lk.search_targetpixelfile('TIC '+str(ticid), mission='TESS', author='SPOC', exptime=exptime, sector=sector).download(download_dir=download_dir)
        return x
            


    def _get_metadata(tpf, outdir='/Users/veraberger/nasa/meta_training/'): 
        """ Get relevant metadata from the headers of a TESS TargetPixelFile object
            If outdir is specified, save the array into an .npy file

        Parameters
        ----------
        outdir : str
            Directory to save metadata into
        
        Returns
        -------
        nothing - do i say that or just leave this blank?
        """
        metaArr = np.array([tpf.ra, tpf.dec,  tpf.get_header()['TESSMAG'], tpf.get_header()['TEFF'],  tpf.get_header()['RADIUS'], tpf.sector, tpf.hdu[1].header['CDPP1_0'],  tpf.hdu[1].header['CROWDSAP'], tpf.camera, tpf.ccd,  tpf.get_header()['LOGG']])
        if outdir is not None:
            np.save(outdir+str(tpf.targetid)+'_'+str(tpf.sector)+'_meta.npy', metaArr)
        else:
            return metaArr


    def _get_centroid_shift(self):
        """
        Retrieves the centroid time series from a TargetPixelFile, 
        returns the magnitude of the 2D shift of the centroid from the median

        Parameters
        ----------
        outdir : str
            Directory to save metadata into
        
        Returns
        -------
        Square root of sum of squares of the centroid row and column time series
        """
        c_cols, c_rows = self.estimate_centroids(aperture_mask='default', method='moments')
        # subtract median from centroid ts and calculate the magnitude of the shift of the centroid from the median at each cadence
        c_cols -= np.nanmedian(c_cols)
        c_rows -= np.nanmedian(c_rows)
        return np.sqrt(c_cols**2+c_rows**2).value

    def _get_pos_corr(self):
        # magnitude of vector given by poscorr 1 and 2
        return np.sqrt(self.pos_corr1**2+self.pos_corr2**2) 
    
    
    def _tpf_to_lc(self, cr=True):
        print(self.exptime)
        lc = self.to_lightcurve(aperture_mask=self.pipeline_mask)
        if cr == True:
            if not self.exptime == 20:
                raise TypeError("Cosmic ray injection is only possible for 20-second datasets.")
            cosmic_ray_cube = load_cosmicray_extension(self) 
            tpf_cr = (self+cosmic_ray_cube)
            lc_cr = tpf_cr.to_lightcurve(aperture_mask=self.pipeline_mask)
            crArr = np.where(lc_cr.flux - lc.flux != 0, 1, 0)
            return lc_cr, crArr
        else: 
            return lc


    def _make_orbit_files(lc, datadir, crArr, pos_corr, c_dist):
        df = pd.DataFrame(data=[lc.time.value, lc.flux.value, lc.flux_err.value, lc.quality.value, pos_corr, c_dist, crArr]).T
        dt = df[0].diff()
        gap_index = df.index[dt == dt.max()].item()
        orbit1 = df.iloc[:gap_index]
        orbit2 = df.iloc[gap_index:]
        np.save(datadir+str(lc.targetid)+'_'+str(lc.sector)+'_1_data.npy', np.asarray(orbit1))
        np.save(datadir+str(lc.targetid)+'_'+str(lc.sector)+'_2_data.npy', np.asarray(orbit2))

    
    def training_data_generator(lc_list, batch_size=32, window_size=100):
        # here lc_list is a list of filenames in the training set
        for fname in lc_list:
            target_data = np.load(fname)

            target_lc = target_data[1] # flux array
            labels = target_data[7] # flare array

            lc_length = len(target_lc)
            valid_indices = np.arange(int(window_size/2), int(lc_length-window_size/2), dtype=int)

            # Note I've shuffled the indices for training so the batch isn't all sampling the same part of the lc
            # We don't need/want to do this for prediction. This can become an input flag (unless we design a separate generator for the prediction)
            np.random.shuffle(valid_indices)
            j = 0 #J loops through the time series for a single target
            while j+batch_size <= len(valid_indices):
                data = np.empty((batch_size, window_size, 1))
                #print(data.shape)
                label = np.empty((batch_size), dtype=int)
                for k in range(batch_size):
                    #print(i, j, k)
                    X = target_lc[valid_indices[j+k]-int(window_size/2) : valid_indices[j+k]+int(window_size/2)].reshape(window_size,1)
                    data[k,] = RobustScaler().fit_transform(X)
                    label[k] = np.asarray(labels[j+k])
                    #print(data[k,])
                    #print(label)
                #print(data.shape, label)
                yield data, label
                j = j + batch_size





tpf = InputTPF.download_tpf(10863087, sector=30, exptime=20, download_dir='ward/ward_tpfs/')
print(tpf)
print(type(tpf))
tpf._tpf_to_lc() # this does not work
