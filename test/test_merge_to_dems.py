"""merge_to_dems()関数をテストする

Python 3.9
dems   0.4.0

(C) 2023 内藤システムズ
"""
import os
import sys

sys.path.append('../')

import unittest
import dfits2dems as dd
import numpy      as np
import xarray     as xa
import pandas     as pd
import math

import merge_function as mf
import merge_to_dems  as mtd

from astropy.io     import fits
from dems.d2        import MS
from merge_to_dfits import MergeToDfits
from datetime       import datetime

class MergeToDemsTestDrive(unittest.TestCase):
    """merge_to_dems.pyモジュールの単体テスト"""
    def setUp(self):
        self.obsid = '20171103184436'
        self.reduced_fits = 'cache/{0}/reduced_{0}.fits'.format(self.obsid)
        self.dfits = 'cache/{0}/dfits_{0}.fits.gz'.format(self.obsid)
        return

    def test_merge_to_dems(self):
        prefix = 'testdata'

        n_time = None
        n_kid  = None
        times  = None
        with fits.open('testdata_reduced_readout.fits') as hdul:
            n_time = hdul['READOUT'].header['NAXIS2']
            n_kid  = hdul['KIDSINFO'].header['NAXIS2']
            times  = np.array(mf.convert_timestamp(hdul['READOUT'].data['timestamp'])).astype(np.datetime64)
            kidids = np.array(hdul['KIDSINFO'].data['kidid']).astype(np.int64)

        dems = mtd.merge_to_dems(
            ddbfits_path='{}_DDB.fits.gz'.format(prefix),
            obsinst_path='../data/deshima2.0/cosmos_{0}/{0}.obs'.format(self.obsid),
            antenna_path='{}.ant'.format(prefix),
            readout_path='{}_reduced_readout.fits'.format(prefix),
            skychop_path='{}.skychop'.format(prefix),
            weather_path='{}.wea'.format(prefix),
            misti_path='{}.misti'.format(prefix),
            cabin_path='{}.cabin'.format(prefix),
        )
        self.assertEqual(xa.DataArray, type(dems), 'demsオブジェクトの型の確認')

        #
        # MS::data(Tsignal)の計算の試験
        #
        # merge_function.pyに定義されているcalibrate_to_power()関数で計算される。
        #
        # f_shift = (linPh - linyfc)/(4*Qr)
        #
        # Tlos_model = ( f_shift + p0*sqrt(Troom + T0) )**2 / (p0**2 * etaf) - T0/etaf - ((1 - etaf)/etaf)*Tamb
        #
        # ここでtdmaker.pyのTestDataMaker()クラスで単純な以下のようなテストデータ与えられる。これらの値は0による割り算が発生しないように適当に選ばれている。
        # linPh  = 1.0
        # linyfc = 0.2
        # Qr     = 1.1
        # p0     = 1.0
        # etaf   = 0.5
        # T0     = 1.0
        # Troom  = 273.15 + 15 ( = T_lower_cabin)
        # Tamb   = 273.15 + 15 ( = weather temperature)
        #
        # 上記の値で計算すると以下のようになる。
        # f_shift    =  2/11
        # Tlos_model = (2/11 + sqrt(289.15))**2/0.5 - 2 - 288.15
        #
        # この結果をfloat32表現するとdataの値に一致する。
        #
        expected = np.array([((2/11 + np.sqrt(289.15))**2)/0.5 - 2 - 288.15]).astype(np.float32) # 注意 float32
        self.assertEqual(round(expected[0], 4), round(dems.data[0][0], 4), 'MS::dataの計算値が正しいことを確認')
        self.assertEqual(n_time, len(dems.data),       'dems.dataの打刻数の確認')
        self.assertEqual(n_kid,  len(dems.data[0]),    'dems.dataのチャネル数の確認')

        # MS::mask (既定値)
        self.assertFalse(dems.mask[0 ][0 ], 'maskに既定値が格納されていることを確認[ 0, 0]')
        self.assertFalse(dems.mask[0 ][-1], 'maskに既定値が格納されていることを確認[ 0,-1]')
        self.assertFalse(dems.mask[-1][-1], 'maskに既定値が格納されていることを確認[-1,-1]')
        self.assertFalse(dems.mask[-1][0 ], 'maskに既定値が格納されていることを確認[-1, 0]')
        self.assertTrue(np.array(dems.mask == False).all(), '全maskに既定値が格納されていることを確認')

        # MS::weight (既定値)
        self.assertEqual(1.0, dems.weight[0 ][0 ], 'weightに既定値が格納されていることを確認[ 0, 0]')
        self.assertEqual(1.0, dems.weight[0 ][-1], 'weightに既定値が格納されていることを確認[ 0,-1]')
        self.assertEqual(1.0, dems.weight[-1][-1], 'weightに既定値が格納されていることを確認[-1,-1]')
        self.assertEqual(1.0, dems.weight[-1][0 ], 'weightに既定値が格納されていることを確認[-1, 0]')
        self.assertTrue(np.array(dems.weight == 1.0).all(), '全weightに既定値が格納されていることを確認')
        
        # MS::time
        self.assertEqual(n_time, len(dems.time),            'MS::timeの打点数の確認')
        self.assertTrue(np.array(times == dems.time).all(), '時刻がREADOUTの打刻と一致することを確認')
        self.assertEqual(times[0],  dems.time.values[0],    'demsの開始時刻が元のデータに一致することを確認')
        self.assertEqual(times[-1], dems.time.values[-1],   'demsの終了時刻が元のデータに一致することを確認')

        # MS::chan
        self.assertEqual(n_kid, len(dems.chan),              'チャネル数の確認')
        self.assertTrue(np.array(kidids == dems.chan).all(), 'KIDIDがチャネル番号と一致することを確認')

        # MS::beam (既定値)
        self.assertEqual(n_time, len(dems.beam),         'MS::beamの打点数が打刻数に一致することを確認')
        self.assertTrue(np.array(dems.beam == '').all(), 'MS::beamに既定値が格納されていることを確認')

        # MS::scan (既定値)
        self.assertEqual(n_time, len(dems.scan),         'MS::scanの打点数が打刻数に一致することを確認')
        self.assertTrue(np.array(dems.scan == '').all(), 'MS::scanに既定値が格納されていることを確認')

        # MS::state
        #
        # stateはTestDataMaker()によって前半にGRAD、後半にONが格納されるようになっている。
        #
        self.assertEqual(n_time, len(dems.state), 'MS::stateの打点数が打刻数に一致することを確認')
        self.assertEqual(0.5, round(np.count_nonzero(dems.state == 'GRAD')/n_time, 1), 'MS::stateのおよそ半数がGRADであることを確認')
        self.assertEqual(0.5, round(np.count_nonzero(dems.state == 'ON')/n_time, 1),   'MS::stateのおよそ半数がONであることを確認')
        self.assertEqual('GRAD', dems.state[0],  'MS::stateの最初の要素がGRADであることを確認')
        self.assertEqual('ON',   dems.state[-1], 'MS::stateの最後の要素がONであることを確認')

        # この操作は非常に時間がかかる
        # n_state_change = 0
        # prev = dems.state[0]
        # for state in dems.state:
        #     if (prev != state):
        #         n_state_change += 1
        #     prev = state
        # self.assertEqual(1, n_state_change, 'MS::stateの切り替えが1回だけ発生していることを確認')

        # MS::lon
        #
        # coordinate = azel, loadmode = 0 の場合
        #
        # lon = -2.1*cos(deg2rad(lat))
        # lat = -2.1
        #
        self.assertTrue(np.array(dems.lon != 0).all(), 'MS::lonが既定値ではないことを確認')
        self.assertEqual(-2.1*np.cos(np.deg2rad(-2.1)), dems.lon.values[0], 'MS::lonの計算値が正しいことを確認')

        # MS::lat
        self.assertTrue(np.array(dems.lat != 0).all(), 'MS::latが既定値ではないことを確認')
        self.assertEqual(-2.1, dems.lat.values[0],     'MS::latの計算値が正しいことを確認')

        # MS::lon_origin
        self.assertTrue(np.array(dems.lon_origin != 0).all(),    'MS::lon_originが既定値ではないことを確認')
        self.assertTrue(np.array(dems.lon_origin == 1.1).all() , 'MS::lon_originの計算値が正しいことを確認')

        # MS::lat_origin
        self.assertTrue(np.array(dems.lat_origin != 0).all(),   'MS::lat_originが既定値ではないことを確認')
        self.assertTrue(np.array(dems.lat_origin == 1.1).all(), 'MS::lat_originの計算値が正しいことを確認')

        # MS::frame
        self.assertEqual('altaz', dems.frame, 'MS::frameが既定値であることを確認')

        # Weather Informations
        self.assertTrue(np.array(dems.temperature    == 15.0).all(), 'MS::temperatureが既定値でないことを確認')
        self.assertTrue(np.array(dems.pressure       == 15.0).all(), 'MS::pressureが既定値でないことを確認')
        self.assertTrue(np.array(dems.humidity       == 15.0).all(), 'MS::humidityが既定値でないことを確認')
        self.assertTrue(np.array(dems.wind_speed     == 15.0).all(), 'MS::wind_speedが既定値でないことを確認')
        self.assertTrue(np.array(dems.wind_direction == 15.0).all(), 'MS::wind_directionが既定値でないことを確認')

        # Data Informations
        #
        # 注意
        # beam_major, beam_minor, beam_pa, exposure, intervalは固定値。
        # MergeToDfits()クラスでも固定値が指定されていた。
        #
        self.assertTrue(np.array(dems.bandwidth  == 0.0).all(),   'MS::bandwidthが既定値であることを確認')
        self.assertTrue(np.array(dems.frequency  == 0.0).all(),   'MS::frequencyが既定値であることを確認')
        self.assertTrue(np.array(dems.beam_major == 0.005).all(), 'MS::beam_majorが既定値で無いことを確認')
        self.assertTrue(np.array(dems.beam_minor == 0.005).all(), 'MS::beam_minorが既定値で無いことを確認')
        self.assertTrue(np.array(dems.beam_pa    == 0.005).all(), 'MS::beam_paが既定値で無いことを確認')
        self.assertTrue(np.array(dems.exposure   == 1/196).all(), 'MS::exposureが既定値で無いことを確認')
        self.assertTrue(np.array(dems.interval   == 1/196).all(), 'MS::intervalが既定値で無いことを確認')

        # Observation Informations
        self.assertEqual(dems.observation,    'saturn_zscan_v05_2_rtn_pattern6', 'MS::observer')
        self.assertEqual(dems.observer,       'clumsy', 'MS::observer')
        self.assertEqual(dems.object,         'SATURN', 'MS::object')
        self.assertEqual(dems.telescope_name, 'ASTE',   'MS::telescope_name')
        self.assertEqual(dems.telescope_diameter, 10.0, 'MS::telescope_diameterが既定値であることを確認')

        expected = (+2230817.2140945992, -5440188.022176585, -2475718.801708271)
        self.assertEqual(dems.telescope_coordinates, expected, 'MS::telescope_coordinatesが既定値であることを確認')

        # ASTE Specific
        self.assertTrue(np.array(dems.aste_cabin_temperature == 15.0 + 273.15).all(), 'MS::aste_cabin_temperatureが既定値でないことを確認')
        self.assertTrue((dems.aste_misti_lon.values == 180).all(),  'MS::aste_misti_lonが既定値で無いことを確認')
        self.assertTrue((dems.aste_misti_lat.values == 90).all(),   'MS::aste_misti_latが既定値で無いことを確認')
        self.assertTrue((dems.aste_misti_pwv.values == 0.61).all(), 'MS::aste_misti_pwvが既定値で無いことを確認')
        self.assertEqual('altaz', dems.aste_misti_frame,     'MS::aste_misti_frameが既定値であることを確認')

        # DESHIMA 2.0 specific
        self.assertTrue(np.array(dems.d2_mkid_id != 0).any())
        self.assertTrue(np.array(dems.d2_mkid_type != '').all())
        self.assertTrue(np.array(dems.d2_mkid_frequency == 1.5).all(), 'd2_mkid_frequencyの値を確認(DDB.KIDDES.F_filter)')
        self.assertTrue(np.array(dems.d2_roomchopper_isblocking == False).all(), 'd2_roomchopper_isblockingの値が既定値であることを確認')
        self.assertTrue(np.array(dems.d2_skychopper_isblocking == False).any(), 'd2_skychopper_isblockingの値が既定値で無いことを確認')
        self.assertTrue(np.array(dems.d2_skychopper_isblocking == True).any(), 'd2_skychopper_isblockingの値が既定値で無いことを確認')
        self.assertEqual(0.5, round(np.count_nonzero(dems.d2_skychopper_isblocking == False)/n_time, 1), 'MS::d2_skychopper_isblockingのおよそ半数がFalseであることを確認')
        self.assertEqual(0.5, round(np.count_nonzero(dems.d2_skychopper_isblocking == True)/n_time, 1),  'MS::d2_skychopper_isblockingのおよそ半数がTrueであることを確認')
        self.assertEqual('0.4.0', dems.d2_dems_version)
        self.assertEqual('1.0.0', dems.d2_dmerge_version)
        return

if __name__=='__main__':
    unittest.main()
