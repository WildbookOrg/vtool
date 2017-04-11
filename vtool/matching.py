# -*- coding: utf-8 -*-
"""
    vt
    python -m utool.util_inspect check_module_usage --pat="matching.py"

"""
from __future__ import absolute_import, division, print_function
import six
import warnings
import utool as ut
import numpy as np
from collections import namedtuple
(print, rrr, profile) = ut.inject2(__name__)

MatchTup3 = namedtuple('MatchTup3', ('fm', 'fs', 'fm_norm'))
MatchTup2 = namedtuple('MatchTup2', ('fm', 'fs'))
AssignTup = namedtuple('AssignTup', ('fm', 'match_dist', 'norm_fx1', 'norm_dist'))


# maximum SIFT matching distance based using uint8 trick from hesaff
PSEUDO_MAX_VEC_COMPONENT = 512
PSEUDO_MAX_DIST_SQRD = 2 * (PSEUDO_MAX_VEC_COMPONENT ** 2)
PSEUDO_MAX_DIST = np.sqrt(2) * (PSEUDO_MAX_VEC_COMPONENT)

TAU = 2 * np.pi  # tauday.org


class MatchingError(Exception):
    pass


VSONE_ASSIGN_CONFIG = [
    ut.ParamInfo('checks', 20),
    ut.ParamInfo('symmetric', False),
    ut.ParamInfo('weight', None, valid_values=[None, 'fgweights'],),
    ut.ParamInfo('K', 1, min_=1),
    ut.ParamInfo('Knorm', 1, min_=1),
]

VSONE_RATIO_CONFIG = [
    ut.ParamInfo('ratio_thresh', .625, min_=0.0, max_=1.0),
]


VSONE_SVER_CONFIG = [
    ut.ParamInfo('sv_on', True),
    ut.ParamInfo('refine_method', 'homog', valid_values=['homog', 'affine'],
                 hideif=lambda cfg: not cfg['sv_on']),
    ut.ParamInfo('sver_xy_thresh', .01, min_=0.0, max_=None,
                 hideif=lambda cfg: not cfg['sv_on']),
    ut.ParamInfo('sver_ori_thresh', TAU / 4.0, min_=0.0, max_=TAU,
                 hideif=lambda cfg: not cfg['sv_on']),
    ut.ParamInfo('sver_scale_thresh', 2.0, min_=1.0, max_=None,
                 hideif=lambda cfg: not cfg['sv_on']),

]

VSONE_DEFAULT_CONFIG = (
    VSONE_ASSIGN_CONFIG + VSONE_RATIO_CONFIG + VSONE_SVER_CONFIG
)

VSONE_PI_DICT = {
    pi.varname: pi for pi in VSONE_DEFAULT_CONFIG
}


@ut.reloadable_class
class PairwiseMatch(ut.NiceRepr):
    """
    Newest (Sept-16-2016) object oriented one-vs-one matching interface

    Creates an object holding two annotations
    Then a pipeline of operations can be applied to
    generate score and refine the matches

    Note:
        The annotation dictionaries are required to have certain attributes.

        Required annotation attributes:
            (kpts, vecs) OR rchip OR rchip_fpath

        Optional annotation attributes:
            aid, nid, flann, rchip, dlen_sqrd, weight
    """
    def __init__(match, annot1=None, annot2=None):
        match.annot1 = annot1
        match.annot2 = annot2
        match.fm = None
        match.fs = None
        match.H_21 = None
        match.H_12 = None

        match.local_measures = ut.odict([])
        match.global_measures = ut.odict([])
        match._inplace_default = False

    @staticmethod
    def _take_params(config, keys):
        """
        take parameter info from config using default values defined in module
        constants.
        """
        # if isinstance(keys, six.string_types):
        #     keys = keys.split(', ')
        return [config.get(key, VSONE_PI_DICT[key].default) for key in keys]

    def __getstate__(match):
        # The state ignores most of the annotation objects
        _annot1 = {}
        if 'aid' in match.annot1:
            _annot1['aid'] = match.annot1['aid']
        _annot2 = {}
        if 'aid' in match.annot2:
            _annot2['aid'] = match.annot2['aid']
        state = {
            'annot1': _annot1,
            'annot2': _annot2,
            'fm': match.fm,
            'fs': match.fs,
            'H_21': match.H_21,
            'H_12': match.H_12,
            'global_measures': match.global_measures,
            'local_measures': match.local_measures,
        }
        return state

    def __setstate__(match, state):
        match.__dict__.update(state)

    def show(match, ax=None, show_homog=False, show_ori=True, show_ell=True,
             show_pts=True, show_lines=True, show_rect=False, show_eig=False,
             show_all_kpts=False, mask_blend=0, overlay=True):
        import plottool as pt
        annot1 = match.annot1
        annot2 = match.annot2
        rchip1 = annot1['rchip']
        rchip2 = annot2['rchip']

        if overlay:
            kpts1 = annot1['kpts']
            kpts2 = annot2['kpts']
        else:
            kpts1 = kpts2 = None
            show_homog = False
            show_ori = False
            show_ell = False
            show_pts = False
            show_lines = False
            show_rect = False
            show_eig = False
            # show_all_kpts = False
            # mask_blend = 0

        if mask_blend:
            import vtool as vt
            mask1 = vt.resize(annot1['probchip_img'], vt.get_size(rchip1))
            mask2 = vt.resize(annot2['probchip_img'], vt.get_size(rchip2))
            # vt.blend_images_average(vt.mask1, 1.0, alpha=mask_blend)
            rchip1 = vt.blend_images_mult_average(rchip1, mask1, alpha=mask_blend)
            rchip2 = vt.blend_images_mult_average(rchip2, mask2, alpha=mask_blend)
        fm = match.fm
        fs = match.fs

        H1 = match.H_12 if show_homog else None
        # H2 = match.H_21 if show_homog else None

        ax, xywh1, xywh2 = pt.show_chipmatch2(
            rchip1, rchip2, kpts1, kpts2, fm, fs, colorbar_=False,
            H1=H1, ax=ax,
            ori=show_ori, rect=show_rect, eig=show_eig, ell=show_ell,
            pts=show_pts, draw_lines=show_lines,
            all_kpts=show_all_kpts,
        )
        return ax, xywh1, xywh2

    def ishow(match):
        """
        CommandLine:
            python -m vtool.matching ishow

        Example:
            >>> # SCRIPT
            >>> from vtool.matching import *  # NOQA
            >>> from vtool.inspect_matches import lazy_test_annot
            >>> import vtool as vt
            >>> annot1 = lazy_test_annot('easy1.png')
            >>> annot2 = lazy_test_annot('easy2.png')
            >>> match = vt.PairwiseMatch(annot1, annot2)
            >>> self = match.ishow()
            >>> ut.quit_if_noshow()
        """
        from vtool.inspect_matches import MatchInspector
        self = MatchInspector(match=match)
        self.show()
        return self

    def add_global_measures(match, global_keys):
        for key in global_keys:
            match.global_measures[key] = (match.annot1[key],
                                          match.annot2[key])

    def add_local_measures(match, xy=True, scale=True):
        import vtool as vt
        if xy:
            key_ = 'norm_xys'
            norm_xy1 = match.annot1[key_].take(match.fm.T[0], axis=1)
            norm_xy2 = match.annot2[key_].take(match.fm.T[1], axis=1)
            match.local_measures['norm_x1'] = norm_xy1[0]
            match.local_measures['norm_y1'] = norm_xy1[1]
            match.local_measures['norm_x2'] = norm_xy2[0]
            match.local_measures['norm_y2'] = norm_xy2[1]
        if scale:
            kpts1_m = match.annot1['kpts'].take(match.fm.T[0], axis=0)
            kpts2_m = match.annot2['kpts'].take(match.fm.T[1], axis=0)
            match.local_measures['scale1'] = vt.get_scales(kpts1_m)
            match.local_measures['scale2'] = vt.get_scales(kpts2_m)

    def __nice__(match):
        parts = []
        if 'aid' in match.annot1:
            aid1 = match.annot1['aid']
            aid2 = match.annot2['aid']
            vsstr = '%s-vs-%s' % (aid1, aid2)
            parts.append(vsstr)
        parts.append('None' if match.fm is None else
                     six.text_type(len(match.fm)))
        return ' '.join(parts)

    def __len__(match):
        if match.fm is not None:
            return len(match.fm)
        else:
            return 0

    def matched_vecs2(match):
        return match.annot2['vecs'].take(match.fm.T[1], axis=0)

    def _next_instance(match, inplace=None):
        """
        Returns either the same or a new instance of a match object with the
        same global attributes.
        """
        if inplace is None:
            inplace = match._inplace_default
        if inplace:
            match_ = match
        else:
            match_ = match.__class__(match.annot1, match.annot2)
            match_.H_21 = match.H_21
            match_.H_12 = match.H_12
            match_._inplace_default = match._inplace_default
            match_.global_measures = match.global_measures.copy()
        return match_

    def copy(match):
        match_ = match._next_instance(inplace=False)
        if match.fm is not None:
            match_.fm = match.fm.copy()
            match_.fs = match.fs.copy()
        match_.local_measures = ut.map_vals(
                lambda a: a.copy(), match.local_measures)
        return match_

    def compress(match, flags, inplace=None):
        match_ = match._next_instance(inplace)
        match_.fm = match.fm.compress(flags, axis=0)
        match_.fs = match.fs.compress(flags, axis=0)
        match_.local_measures = ut.map_vals(
                lambda a: a.compress(flags), match.local_measures)
        return match_

    def take(match, indicies, inplace=None):
        match_ = match._next_instance(inplace)
        match_.fm = match.fm.take(indicies, axis=0)
        match_.fs = match.fs.take(indicies, axis=0)
        match_.local_measures = ut.map_vals(
                lambda a: a.take(indicies), match.local_measures)
        return match_

    def assign(match, cfgdict={}, verbose=None):
        """
        Assign feature correspondences between annots

        >>> from vtool.matching import *  # NOQA
        """
        params = match._take_params(cfgdict, ['K', 'Knorm', 'symmetric',
                                              'checks', 'weight'])
        K, Knorm, symmetric, checks, weight_key = params
        annot1 = match.annot1
        annot2 = match.annot2

        ensure_metadata_vsone(annot1, annot2, cfgdict)

        if verbose is None:
            verbose = True

        num_neighbors = K + Knorm

        # Search for nearest neighbors
        fx2_to_fx1, fx2_to_dist = normalized_nearest_neighbors(
            annot1['flann'], annot2['vecs'], num_neighbors, checks)
        if symmetric:
            fx1_to_fx2, fx1_to_dist = normalized_nearest_neighbors(
                annot2['flann'], annot1['vecs'], num_neighbors, checks)
            valid_flags = flag_symmetric_matches(fx2_to_fx1, fx1_to_fx2, K)
        else:
            valid_flags = np.ones((len(fx2_to_fx1), K), dtype=np.bool)

        # Assign matches
        assigntup = assign_unconstrained_matches(fx2_to_fx1, fx2_to_dist, K,
                                                 Knorm, valid_flags)
        fm, match_dist, fx1_norm, norm_dist = assigntup
        ratio = np.divide(match_dist, norm_dist)
        ratio_score = (1.0 - ratio)

        # remove local measure that can no longer apply
        ut.delete_dict_keys(match.local_measures, ['sver_err_xy',
                                                   'sver_err_scale',
                                                   'sver_err_ori'])

        match.local_measures['match_dist'] = match_dist
        match.local_measures['norm_dist'] = norm_dist
        match.local_measures['ratio'] = ratio

        if weight_key is None:
            match.fs = ratio_score
        else:
            weight1 = annot1[weight_key].take(fm.T[0], axis=0)
            weight2 = annot2[weight_key].take(fm.T[1], axis=0)
            weight = np.sqrt(weight1 * weight2)
            weighted_ratio = ratio_score * weight

            match.local_measures[weight_key] = weight
            match.local_measures['weighted_ratio'] = weighted_ratio
            match.local_measures['weighted_norm_dist'] = norm_dist * weight
            match.fs = weighted_ratio

        match.fm = fm
        match.fm_norm = np.vstack([fx1_norm, fm.T[1]]).T
        return match

    def ratio_test_flags(match, cfgdict={}):
        ratio_thresh = match._take_params(cfgdict, ['ratio_thresh'])[0]
        ratio = match.local_measures['ratio']
        flags = np.less(ratio, ratio_thresh)
        return flags

    def sver_flags(match, cfgdict={}, return_extra=False):
        from vtool import spatial_verification as sver
        import vtool as vt
        params = match._take_params(
            cfgdict, ['sver_xy_thresh', 'sver_ori_thresh', 'sver_scale_thresh',
                      'refine_method'])
        sver_xy_thresh, sver_ori_thresh, sver_scale_thresh, refine_method = params

        kpts1 = match.annot1['kpts']
        kpts2 = match.annot2['kpts']
        dlen_sqrd2 = match.annot2['dlen_sqrd']
        fm = match.fm

        # match_weights = np.ones(len(fm))
        match_weights = match.fs
        svtup = sver.spatially_verify_kpts(
            kpts1, kpts2, fm,
            xy_thresh=sver_xy_thresh,
            ori_thresh=sver_ori_thresh,
            scale_thresh=sver_scale_thresh,
            dlen_sqrd2=dlen_sqrd2,
            match_weights=match_weights,
            refine_method=refine_method)
        if svtup is None:
            errors = [np.empty(0), np.empty(0), np.empty(0)]
            inliers = []
            H_12 =  np.eye(3)
        else:
            (inliers, errors, H_12) = svtup[0:3]

        flags = vt.index_to_boolmask(inliers, len(fm))

        if return_extra:
            return flags, errors, H_12
        else:
            return flags

    def apply_all(match, cfgdict):
        match.H_21 = None
        match.H_12 = None
        match.local_measures = ut.odict([])
        match.assign(cfgdict)
        match.apply_ratio_test(cfgdict, inplace=True)
        sv_on = match._take_params(cfgdict, ['sv_on'])[0]

        if sv_on:
            match.apply_sver(cfgdict, inplace=True)

    def apply_ratio_test(match, cfgdict={}, inplace=None):
        flags = match.ratio_test_flags(cfgdict)
        match_ = match.compress(flags, inplace=inplace)
        return match_

    def apply_sver(match, cfgdict={}, inplace=None):
        flags, errors, H_12 = match.sver_flags(cfgdict,
                                               return_extra=True)
        match_ = match.compress(flags, inplace=inplace)
        errors_ = [e.compress(flags) for e in errors]
        match_.local_measures['sver_err_xy'] = errors_[0]
        match_.local_measures['sver_err_scale'] = errors_[1]
        match_.local_measures['sver_err_ori'] = errors_[2]
        match_.H_12 = H_12
        return match_

    def _make_global_feature_vector(match, global_keys=None):
        """ Global annotation properties and deltas """
        import vtool as vt
        feat = ut.odict([])

        if global_keys is None:
            # FIXME: speed
            global_keys = sorted(match.global_measures.keys())
        global_measures = ut.dict_subset(match.global_measures, global_keys)

        for k, v in global_measures.items():
            v1, v2 = v
            if v1 is None:
                v1 = np.nan
            if v2 is None:
                v2 = np.nan
            if ut.isiterable(v1):
                for i in range(len(v1)):
                    feat['global(%s_1[%d])' % (k, i)] = v1[i]
                    feat['global(%s_2[%d])' % (k, i)] = v2[i]
                if k == 'gps':
                    delta = vt.haversine(v1, v2)
                else:
                    delta = np.abs(v1 - v2)
            else:
                feat['global(%s_1)' % (k,)] = v1
                feat['global(%s_2)' % (k,)] = v2
                if k == 'yaw':
                    delta = vt.ori_distance(v1, v2)
                else:
                    delta = np.abs(v1 - v2)
            feat['global(%s_delta)' % (k,)] = delta

        if 'global(gps_delta)' in feat and 'global(time_delta)' in feat:
            hour_delta = feat['global(time_delta)'] / 360
            feat['global(speed)'] = feat['global(gps_delta)'] / hour_delta
        return feat

    def _make_local_summary_feature_vector(match, local_keys=None,
                                           summary_ops=None, bin_key=None,
                                           bins=4):
        r"""
        Summary statistics of local features

        CommandLine:
            python -m vtool.matching make_feature_vector

        Example:
            >>> # ENABLE_DOCTEST
            >>> from vtool.matching import *  # NOQA
            >>> from vtool.inspect_matches import lazy_test_annot
            >>> import vtool as vt
            >>> annot1 = lazy_test_annot('easy1.png')
            >>> annot2 = lazy_test_annot('easy2.png')
            >>> match = vt.PairwiseMatch(annot1, annot2)
            >>> cfgdict = {'ratio_thresh': .95, 'sv_on': False}
            >>> match.apply_all(cfgdict)
            >>> summary_ops = {'len', 'sum'}
            >>> bin_key = 'ratio'
            >>> bins = 4
            >>> bins = [.5, .625, .7, .9]
            >>> local_keys = ['ratio', 'norm_dist']
            >>> feat = match._make_local_summary_feature_vector(
            >>>     local_keys=local_keys,
            >>>     bin_key=bin_key, summary_ops=summary_ops, bins=bins)
            >>> result = ('feat = %s' % (ut.repr2(feat, nl=2),))
            >>> print(result)
        """
        if summary_ops is None:
            summary_ops = {'sum', 'mean', 'std', 'len'}
        if local_keys is None:
            local_measures = match.local_measures
        else:
            local_measures = ut.dict_subset(match.local_measures, local_keys)

        ops = {
            # 'len'    : len,
            'sum'    : np.sum,
            'mean'   : np.mean,
            'median' : np.median,
            'std'    : np.std,
        }

        feat = ut.odict([])
        if bin_key is not None:
            # binned ratio feature vectors
            if isinstance(bins, int):
                bins = np.linspace(0, 1.0, bins + 1)
            else:
                bins = [0] + list(bins)
            local_bin_ids = np.searchsorted(bins, match.local_measures[bin_key])
            dimkey_fmt = '{opname}({measure}[b{binid}])'
            for binid in range(1, len(bins)):
                fxs = np.where(local_bin_ids <= binid)[0]
                if 'len' in summary_ops:
                    dimkey = dimkey_fmt.format(
                        opname='len', measure='matches', binid=binid
                    )
                    feat[dimkey] = len(fxs)
                for opname in sorted(summary_ops - {'len'}):
                    op = ops[opname]
                    for k, vs in local_measures.items():
                        dimkey = dimkey_fmt.format(
                            opname=opname, measure=k, binid=binid
                        )
                        feat[dimkey] = op(vs[fxs])
        else:
            if 'len' in summary_ops:
                feat['len(matches)'] = len(match.fm)
            if 'sum' in summary_ops:
                for k, vs in six.iteritems(local_measures):
                    feat['sum(%s)' % (k,)] = vs.sum()
            if 'mean' in summary_ops:
                for k, vs in six.iteritems(local_measures):
                    feat['mean(%s)' % (k,)] = np.mean(vs)
            if 'std' in summary_ops:
                for k, vs in six.iteritems(local_measures):
                    feat['std(%s)' % (k,)] = np.std(vs)
            if 'med' in summary_ops:
                for k, vs in six.iteritems(local_measures):
                    feat['med(%s)' % (k,)] = np.median(vs)
        return feat

    def _make_local_top_feature_vector(match, local_keys=None, sorters='ratio',
                                       indices=3):
        """ Selected subsets of top features """
        if local_keys is None:
            local_measures = match.local_measures
        else:
            local_measures = ut.dict_subset(match.local_measures, local_keys)

        # Convert indices to an explicit list
        if isinstance(indices, int):
            indices = slice(indices)
        if isinstance(indices, slice):
            # assert indices.stop is not None, 'indices must have maximum value'
            indices = list(range(*indices.indices(len(match.fm))))
            # indices = list(range(*indices.indices(indices.stop)))
        if len(indices) == 0:
            return {}
        # TODO: some sorters might want descending orders
        sorters = ut.ensure_iterable(sorters)
        chosen_xs = [
            match.local_measures[sorter].argsort()[::-1][indices]
            for sorter in sorters
        ]
        feat = ut.odict([
            ('loc[%s,%d](%s)' % (sorter, rank, k), v)
            for sorter, topxs in zip(sorters, chosen_xs)
            for k, vs in six.iteritems(local_measures)
            for rank, v in zip(indices, vs[topxs])
        ])
        return feat

    def make_feature_vector(match, local_keys=None, global_keys=None,
                            summary_ops=None, sorters='ratio', indices=3):
        """
        Constructs the pairwise feature vector that represents a match

        Args:
            local_keys (None): (default = None)
            global_keys (None): (default = None)
            summary_ops (None): (default = None)
            sorters (str): (default = 'ratio')
            indices (int): (default = 3)

        Returns:
            dict: feat

        CommandLine:
            python -m vtool.matching make_feature_vector

        Example:
            >>> # DISABLE_DOCTEST
            >>> from vtool.matching import *  # NOQA
            >>> from vtool.inspect_matches import lazy_test_annot
            >>> import vtool as vt
            >>> annot1 = lazy_test_annot('easy1.png')
            >>> annot2 = lazy_test_annot('easy2.png')
            >>> match = vt.PairwiseMatch(annot1, annot2)
            >>> match.apply_all({})
            >>> feat = match.make_feature_vector(indices=[0, 1])
            >>> result = ('feat = %s' % (ut.repr2(feat, nl=2),))
            >>> print(result)
        """
        feat = ut.odict([])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            feat.update(match._make_global_feature_vector(global_keys))
            feat.update(match._make_local_summary_feature_vector(
                local_keys, summary_ops))
            feat.update(match._make_local_top_feature_vector(
                local_keys, sorters=sorters, indices=indices))
        return feat


def gridsearch_match_operation(matches, op_name, basis):
    import sklearn
    import sklearn.metrics
    y_true = np.array([m.annot1['nid'] == m.annot2['nid'] for m in matches])
    grid = ut.all_dict_combinations(basis)
    auc_list = []
    for cfgdict in ut.ProgIter(grid, lbl='gridsearch', bs=False):
        matches_ = [match.copy() for match in matches]
        y_score = [getattr(m, op_name)(cfgdict=cfgdict).fs.sum()
                   for m in matches_]
        auc = sklearn.metrics.roc_auc_score(y_true, y_score)
        print('cfgdict = %r' % (cfgdict,))
        print('auc = %r' % (auc,))
        auc_list.append(auc)
    print(ut.repr4(ut.sort_dict(ut.dzip(grid, auc_list), 'vals',
                                reverse=True)))
    if len(basis) == 1:
        # interpolate along basis
        pass


def testdata_annot_metadata(rchip_fpath, cfgdict={}):
    metadata = ut.LazyDict({'rchip_fpath': rchip_fpath})
    ensure_metadata_feats(metadata, '', cfgdict)
    return metadata


def ensure_metadata_vsone(annot1, annot2, cfgdict={}):
    ensure_metadata_feats(annot1, cfgdict=cfgdict)
    ensure_metadata_feats(annot2, cfgdict=cfgdict)
    ensure_metadata_flann(annot1, cfgdict=cfgdict)
    ensure_metadata_flann(annot2, cfgdict=cfgdict)
    ensure_metadata_dlen_sqrd(annot2)
    pass


def ensure_metadata_normxy(annot, cfgdict={}):
    import vtool as vt
    if 'norm_xys' not in annot:
        def eval_normxy():
            xys = vt.get_xys(annot['kpts'])
            chip_wh = np.array(annot['chip_size'])[:, None]
            return xys / chip_wh
        annot.set_lazy_func('norm_xys', eval_normxy)


def ensure_metadata_feats(annot, suffix='', cfgdict={}):
    r"""
    Adds feature evaluation keys to a lazy dictionary

    Args:
        annot (utool.LazyDict):
        suffix (str): (default = '')
        cfgdict (dict): (default = {})

    CommandLine:
        python -m vtool.matching --exec-ensure_metadata_feats

    Example:
        >>> # ENABLE_DOCTEST
        >>> from vtool.matching import *  # NOQA
        >>> rchip_fpath = ut.grab_test_imgpath('easy1.png')
        >>> annot = ut.LazyDict({'rchip_fpath': rchip_fpath})
        >>> suffix = ''
        >>> cfgdict = {}
        >>> ensure_metadata_feats(annot, suffix, cfgdict)
        >>> assert len(annot._stored_results) == 1
        >>> annot['kpts']
        >>> assert len(annot._stored_results) == 4
        >>> annot['vecs']
        >>> assert len(annot._stored_results) == 5
    """
    import vtool as vt
    rchip_key = 'rchip' + suffix
    _feats_key = '_feats' + suffix
    kpts_key = 'kpts' + suffix
    vecs_key = 'vecs' + suffix
    rchip_fpath_key = 'rchip_fpath' + suffix

    if rchip_key not in annot:
        def eval_rchip1():
            rchip_fpath1 = annot[rchip_fpath_key]
            return vt.imread(rchip_fpath1)
        annot.set_lazy_func(rchip_key, eval_rchip1)

    if kpts_key not in annot or vecs_key not in annot:
        def eval_feats():
            rchip = annot[rchip_key]
            _feats = vt.extract_features(rchip, **cfgdict)
            return _feats

        def eval_kpts():
            _feats = annot[_feats_key]
            kpts = _feats[0]
            return kpts

        def eval_vecs():
            _feats = annot[_feats_key]
            vecs = _feats[1]
            return vecs
        annot.set_lazy_func(_feats_key, eval_feats)
        annot.set_lazy_func(kpts_key, eval_kpts)
        annot.set_lazy_func(vecs_key, eval_vecs)
    return annot


def ensure_metadata_dlen_sqrd(annot):
    if 'dlen_sqrd' not in annot:
        def eval_dlen_sqrd(annot):
            rchip = annot['rchip']
            dlen_sqrd = rchip.shape[0] ** 2 + rchip.shape[1] ** 2
            return dlen_sqrd
        annot.set_lazy_func('dlen_sqrd', lambda: eval_dlen_sqrd(annot))
    return annot


def ensure_metadata_flann(annot, cfgdict):
    """ setup lazy flann evaluation """
    import vtool as vt
    flann_params = {'algorithm': 'kdtree', 'trees': 8}
    if 'flann' not in annot:
        def eval_flann():
            vecs = annot['vecs']
            if len(vecs) == 0:
                _flann = None
            else:
                _flann = vt.flann_cache(vecs, flann_params=flann_params,
                                        verbose=False)
            return _flann
        annot.set_lazy_func('flann', eval_flann)
    return annot


def empty_neighbors(num_vecs=0, K=0):
    shape = (num_vecs, K)
    fx2_to_fx1 = np.empty(shape, dtype=np.int32)
    _fx2_to_dist_sqrd = np.empty(shape, dtype=np.float64)
    return fx2_to_fx1, _fx2_to_dist_sqrd


def normalized_nearest_neighbors(flann, vecs2, K, checks=800):
    """
    uses flann index to return nearest neighbors with distances normalized
    between 0 and 1 using sifts uint8 trick
    """
    import vtool as vt
    if K == 0:
        (fx2_to_fx1, _fx2_to_dist_sqrd) = empty_neighbors(len(vecs2), 0)
    elif len(vecs2) == 0:
        (fx2_to_fx1, _fx2_to_dist_sqrd) = empty_neighbors(0, K)
    elif flann is None:
        (fx2_to_fx1, _fx2_to_dist_sqrd) = empty_neighbors(0, 0)
    elif K > flann.get_indexed_shape()[0]:
        # Corner case, may be better to throw an assertion error
        raise MatchingError('not enough database features')
        #(fx2_to_fx1, _fx2_to_dist_sqrd) = empty_neighbors(len(vecs2), 0)
    else:
        fx2_to_fx1, _fx2_to_dist_sqrd = flann.nn_index(vecs2, num_neighbors=K,
                                                       checks=checks)
    _fx2_to_dist = np.sqrt(_fx2_to_dist_sqrd.astype(np.float64))
    # normalized dist
    fx2_to_dist = np.divide(_fx2_to_dist, PSEUDO_MAX_DIST)
    fx2_to_fx1 = vt.atleast_nd(fx2_to_fx1, 2)
    fx2_to_dist = vt.atleast_nd(fx2_to_dist, 2)
    return fx2_to_fx1, fx2_to_dist


def assign_spatially_constrained_matches(chip2_dlen_sqrd, kpts1, kpts2, H,
                                         fx2_to_fx1, fx2_to_dist,
                                         match_xy_thresh,
                                         norm_xy_bounds=(0.0, 1.0)):
    r"""
    assigns spatially constrained vsone match using results of nearest
    neighbors.

    Args:
        chip2_dlen_sqrd (dict):
        kpts1 (ndarray[float32_t, ndim=2]):  keypoints
        kpts2 (ndarray[float32_t, ndim=2]):  keypoints
        H (ndarray[float64_t, ndim=2]):  homography/perspective matrix that
            maps image1 space into image2 space
        fx2_to_fx1 (ndarray): image2s nearest feature indices in image1
        fx2_to_dist (ndarray):
        match_xy_thresh (float):
        norm_xy_bounds (tuple):

    Returns:
        tuple: assigntup(
            fx2_match, - matching feature indices in image 2
            fx1_match, - matching feature indices in image 1
            fx1_norm,  - normmalizing indices in image 1
            match_dist, - descriptor distances between fx2_match and fx1_match
            norm_dist, - descriptor distances between fx2_match and fx1_norm
            )

    CommandLine:
        python -m vtool.matching assign_spatially_constrained_matches

    Example:
        >>> # ENABLE_DOCTEST
        >>> from vtool.matching import *  # NOQA
        >>> kpts1 = np.array([[  6.,   4.,   15.84,    4.66,    7.24,    0.  ],
        ...                   [  9.,   3.,   20.09,    5.76,    6.2 ,    0.  ],
        ...                   [  1.,   1.,   12.96,    1.73,    8.77,    0.  ],])
        >>> kpts2 = np.array([[  2.,   1.,   12.11,    0.38,    8.04,    0.  ],
        ...                   [  5.,   1.,   22.4 ,    1.31,    5.04,    0.  ],
        ...                   [  6.,   1.,   19.25,    1.74,    4.72,    0.  ],])
        >>> match_xy_thresh = .37
        >>> chip2_dlen_sqrd = 1400
        >>> norm_xy_bounds = (0.0, 1.0)
        >>> H = np.array([[ 2,  0, 0],
        >>>               [ 0,  1, 0],
        >>>               [ 0,  0, 1]])
        >>> fx2_to_fx1 = np.array([[2, 1, 0],
        >>>                        [0, 1, 2],
        >>>                        [2, 0, 1]], dtype=np.int32)
        >>> fx2_to_dist = np.array([[.40, .80, .85],
        >>>                         [.30, .50, .60],
        >>>                         [.80, .90, .91]], dtype=np.float32)
        >>> # verify results
        >>> assigntup = assign_spatially_constrained_matches(
        >>>     chip2_dlen_sqrd, kpts1, kpts2, H, fx2_to_fx1, fx2_to_dist,
        >>>     match_xy_thresh, norm_xy_bounds)
        >>> fm, fx1_norm, match_dist, norm_dist = assigntup
        >>> result = ut.list_str(assigntup, precision=3, nobr=True)
        >>> print(result)
        np.array([[2, 0],
                  [0, 1],
                  [2, 2]], dtype=np.int32),
        np.array([1, 1, 0], dtype=np.int32),
        np.array([ 0.4,  0.3,  0.8], dtype=np.float32),
        np.array([ 0.8,  0.5,  0.9], dtype=np.float32),
    """
    import vtool as vt
    index_dtype = fx2_to_fx1.dtype
    # Find spatial errors of keypoints under current homography
    # (kpts1 mapped into image2 space)
    fx2_to_xyerr_sqrd = vt.get_match_spatial_squared_error(kpts1, kpts2, H, fx2_to_fx1)
    fx2_to_xyerr = np.sqrt(fx2_to_xyerr_sqrd)
    fx2_to_xyerr_norm = np.divide(fx2_to_xyerr, np.sqrt(chip2_dlen_sqrd))

    # Find matches and normalizers that satisfy spatial constraints
    fx2_to_valid_match      = ut.inbounds(fx2_to_xyerr_norm, 0.0, match_xy_thresh, eq=True)
    fx2_to_valid_normalizer = ut.inbounds(fx2_to_xyerr_norm, *norm_xy_bounds, eq=True)
    fx2_to_fx1_match_col = vt.find_first_true_indices(fx2_to_valid_match)
    fx2_to_fx1_norm_col  = vt.find_next_true_indices(fx2_to_valid_normalizer,
                                                     fx2_to_fx1_match_col)

    assert fx2_to_fx1_match_col != fx2_to_fx1_norm_col, 'normlizers are matches!'

    fx2_to_hasmatch = [pos is not None for pos in fx2_to_fx1_norm_col]
    # IMAGE 2 Matching Features
    fx2_match = np.where(fx2_to_hasmatch)[0].astype(index_dtype)
    match_col_list = np.array(ut.take(fx2_to_fx1_match_col, fx2_match),
                              dtype=fx2_match.dtype)
    norm_col_list = np.array(ut.take(fx2_to_fx1_norm_col, fx2_match),
                             dtype=fx2_match.dtype)

    # We now have 2d coordinates into fx2_to_fx1
    # Covnert into 1d coordinates for flat indexing into fx2_to_fx1
    _match_index_2d = np.vstack((fx2_match, match_col_list))
    _norm_index_2d  = np.vstack((fx2_match, norm_col_list))
    _shape2d        = fx2_to_fx1.shape
    match_index_1d  = np.ravel_multi_index(_match_index_2d, _shape2d)
    norm_index_1d   = np.ravel_multi_index(_norm_index_2d, _shape2d)

    # Find initial matches
    # IMAGE 1 Matching Features
    fx1_match = fx2_to_fx1.take(match_index_1d)
    fx1_norm  = fx2_to_fx1.take(norm_index_1d)
    # compute constrained ratio score
    match_dist = fx2_to_dist.take(match_index_1d)
    norm_dist  = fx2_to_dist.take(norm_index_1d)

    # package and return
    fm = np.vstack((fx1_match, fx2_match)).T
    assigntup = fm, fx1_norm, match_dist, norm_dist
    return assigntup


def assign_unconstrained_matches(fx2_to_fx1, fx2_to_dist, K, Knorm=None,
                                 valid_flags=None):
    """
    assigns vsone matches using results of nearest neighbors.

    Ignore:
        fx2_to_dist = np.arange(fx2_to_fx1.size).reshape(fx2_to_fx1.shape)

    CommandLine:
        python -m vtool.matching --test-assign_unconstrained_matches --show
        python -m vtool.matching assign_unconstrained_matches:0
        python -m vtool.matching assign_unconstrained_matches:1

    Example:
        >>> # ENABLE_DOCTEST
        >>> from vtool.matching import *  # NOQA
        >>> fx2_to_fx1, fx2_to_dist = empty_neighbors(0, 0)
        >>> K = 1
        >>> Knorm = 1
        >>> valid_flags = None
        >>> assigntup = assign_unconstrained_matches(fx2_to_fx1, fx2_to_dist, K,
        >>>                                          Knorm, valid_flags)
        >>> fm, match_dist, norm_fx1, norm_dist = assigntup
        >>> result = ut.list_str(assigntup, precision=3, nobr=True)
        >>> print(result)
        np.array([], shape=(0, 2), dtype=np.int32),
        np.array([], dtype=np.float64),
        np.array([], dtype=np.int32),
        np.array([], dtype=np.float64),

    Example:
        >>> # ENABLE_DOCTEST
        >>> from vtool.matching import *  # NOQA
        >>> fx2_to_fx1 = np.array([[ 77,   971, 22],
        >>>                        [116,   120, 34],
        >>>                        [122,   128, 99],
        >>>                        [1075,  692, 102],
        >>>                        [ 530,   45, 120],
        >>>                        [  45,  530, 77]], dtype=np.int32)
        >>> fx2_to_dist = np.array([[ 0.059,  0.238, .3],
        >>>                         [ 0.021,  0.240, .4],
        >>>                         [ 0.039,  0.247, .5],
        >>>                         [ 0.149,  0.151, .6],
        >>>                         [ 0.226,  0.244, .7],
        >>>                         [ 0.215,  0.236, .8]], dtype=np.float32)
        >>> K = 1
        >>> Knorm = 1
        >>> valid_flags = np.array([[1, 1], [0, 1], [1, 1], [0, 1], [1, 1], [1, 1]])
        >>> valid_flags = valid_flags[:, 0:K]
        >>> assigntup = assign_unconstrained_matches(fx2_to_fx1, fx2_to_dist, K,
        >>>                                          Knorm, valid_flags)
        >>> fm, match_dist, norm_fx1, norm_dist = assigntup
        >>> result = ut.list_str(assigntup, precision=3, nobr=True)
        >>> print(result)
        >>> assert len(fm.shape) == 2 and fm.shape[1] == 2
        >>> assert ut.allsame(list(map(len, assigntup)))
    """
    # Infer the valid internal query feature indexes and ranks
    index_dtype = fx2_to_fx1.dtype

    if valid_flags is None:
        # make everything valid
        flat_validx = np.arange(len(fx2_to_fx1) * K, dtype=index_dtype)
    else:
        #valid_flags = np.ones((len(fx2_to_fx1), K), dtype=np.bool)
        flat_validx = np.flatnonzero(valid_flags)

    match_fx2  = np.floor_divide(flat_validx, K, dtype=index_dtype)
    match_rank = np.mod(flat_validx, K, dtype=index_dtype)

    flat_match_idx = np.ravel_multi_index((match_fx2, match_rank),
                                          dims=fx2_to_fx1.shape)
    match_fx1 = fx2_to_fx1.take(flat_match_idx)
    match_dist = fx2_to_dist.take(flat_match_idx)

    fm = np.vstack((match_fx1, match_fx2)).T

    if Knorm is None:
        basic_norm_rank = -1
    else:
        basic_norm_rank = K + Knorm - 1

    # Currently just use the last one as a normalizer
    norm_rank = np.array([basic_norm_rank] * len(match_fx2),
                         dtype=match_fx2.dtype)
    flat_norm_idx = np.ravel_multi_index((match_fx2, norm_rank),
                                         dims=fx2_to_fx1.shape)
    norm_fx1 = fx2_to_fx1.take(flat_norm_idx)
    norm_dist = fx2_to_dist.take(flat_norm_idx)
    norm_fx1 = fx2_to_fx1[match_fx2, norm_rank]
    norm_dist = fx2_to_dist[match_fx2, norm_rank]

    assigntup = AssignTup(fm, match_dist, norm_fx1, norm_dist)
    return assigntup


def flag_symmetric_matches(fx2_to_fx1, fx1_to_fx2, K=2):
    """
    Example:
        >>> # ENABLE_DOCTEST
        >>> from vtool.matching import *  # NOQA
        >>> fx2_to_fx1 = np.array([[ 0,  1],
        >>>                        [ 1,  4],
        >>>                        [ 3,  4],
        >>>                        [ 2,  0]], dtype=np.int32)
        >>> fx1_to_fx2 = np.array([[ 0, 1],
        >>>                        [ 2, 1],
        >>>                        [ 3, 1],
        >>>                        [ 3, 1],
        >>>                        [ 0, 1]], dtype=np.int32)
        >>> is_symmetric1 = flag_symmetric_matches(fx2_to_fx1, fx1_to_fx2)
        >>> result = ut.array_repr2(is_symmetric1)
        >>> print(result)
        array([[ True, False],
               [ True,  True],
               [False, False],
               [ True, False]], dtype=bool)
    """
    # np.arange(len(fx2_to_fx1), dtype=fx2_to_fx1.dtype)
    match_12 = fx1_to_fx2.T[:K].T
    match_21 = fx2_to_fx1.T[:K].T
    fx2_list = np.arange(len(match_21))
    matched = match_12[match_21.ravel()]
    matched = matched.reshape((len(fx2_to_fx1), K, K))
    flags = matched == fx2_list[:, None, None]
    is_symmetric = np.any(flags, axis=2)
    #is_symmetric = np.any(match_21[match_12.ravel()] == fx2_list, axis=0)
    return is_symmetric


def unconstrained_ratio_match(flann, vecs2, unc_ratio_thresh=.625,
                              fm_dtype=np.int32, fs_dtype=np.float32):
    """ Lowes ratio matching

    from vtool.matching import *  # NOQA
    fs_dtype = rat_kwargs.get('fs_dtype', np.float32)
    fm_dtype = rat_kwargs.get('fm_dtype', np.int32)
    unc_ratio_thresh = rat_kwargs.get('unc_ratio_thresh', .625)

    """
    fx2_to_fx1, fx2_to_dist = normalized_nearest_neighbors(
        flann, vecs2, K=2, checks=800)
    #ut.embed()
    assigntup = assign_unconstrained_matches(fx2_to_fx1, fx2_to_dist, 1)
    fm, fx1_norm, match_dist, norm_dist = assigntup
    ratio_tup = ratio_test(fm, fx1_norm, match_dist, norm_dist,
                           unc_ratio_thresh, fm_dtype=fm_dtype,
                           fs_dtype=fs_dtype)
    return ratio_tup


def spatially_constrained_ratio_match(flann, vecs2, kpts1, kpts2, H, chip2_dlen_sqrd,
                                      match_xy_thresh=1.0, scr_ratio_thresh=.625, scr_K=7,
                                      norm_xy_bounds=(0.0, 1.0),
                                      fm_dtype=np.int32, fs_dtype=np.float32):
    """
    performs nearest neighbors, then assigns based on spatial constraints, the
    last step performs a ratio test.

    H - a homography H that maps image1 space into image2 space
    H should map from query to database chip (1 to 2)
    """
    assert H.shape == (3, 3)
    # Find several of image2's features nearest matches in image1
    fx2_to_fx1, fx2_to_dist = normalized_nearest_neighbors(flann, vecs2, scr_K, checks=800)
    # Then find those which satisfify the constraints
    assigntup = assign_spatially_constrained_matches(
        chip2_dlen_sqrd, kpts1, kpts2, H, fx2_to_fx1, fx2_to_dist,
        match_xy_thresh, norm_xy_bounds=norm_xy_bounds)
    fm, fx1_norm, match_dist, norm_dist = assigntup
    # filter assignments via the ratio test
    scr_tup = ratio_test(fm, fx1_norm, match_dist, norm_dist, scr_ratio_thresh,
                         fm_dtype=fm_dtype, fs_dtype=fs_dtype)
    return scr_tup


def ratio_test(fm, fx1_norm, match_dist, norm_dist,
               ratio_thresh=.625, fm_dtype=np.int32, fs_dtype=np.float32):
    r"""
    Lowes ratio test for one-vs-one feature matches.

    Assumes reverse matches (image2 to image1) and returns (image1 to image2)
    matches. Generalized to accept any match or normalizer not just K=1 and K=2.

    Args:
        fx2_to_fx1 (ndarray): nearest neighbor indices (from flann)
        fx2_to_dist (ndarray): nearest neighbor distances (from flann)
        ratio_thresh (float):
        match_col (int or ndarray): column of matching indices
        norm_col (int or ndarray): column of normalizng indices

    Returns:
        tuple: (fm_RAT, fs_RAT, fm_norm_RAT)

    CommandLine:
        python -m vtool.matching --test-ratio_test

    Example:
        >>> # ENABLE_DOCTEST
        >>> from vtool.matching import *  # NOQA
        >>> fx2_match  = np.array([0, 1, 2, 3, 4, 5], dtype=np.int32)
        >>> fx1_match  = np.array([77, 116, 122, 1075, 530, 45], dtype=np.int32)
        >>> fm = np.vstack((fx1_match, fx2_match)).T
        >>> fx1_norm   = np.array([971, 120, 128, 692, 45, 530], dtype=np.int32)
        >>> match_dist = np.array([ 0.059, 0.021, 0.039, 0.15 , 0.227, 0.216])
        >>> norm_dist  = np.array([ 0.239, 0.241, 0.248, 0.151, 0.244, 0.236])
        >>> ratio_thresh = .625
        >>> ratio_tup = ratio_test(fm, fx1_norm, match_dist, norm_dist, ratio_thresh)
        >>> result = ut.repr3(ratio_tup, precision=3)
        >>> print(result)
        (
            np.array([[ 77,   0],
                      [116,   1],
                      [122,   2]], dtype=np.int32),
            np.array([ 0.753,  0.913,  0.843], dtype=np.float32),
            np.array([[971,   0],
                      [120,   1],
                      [128,   2]], dtype=np.int32),
        )
    """
    fx2_to_ratio = np.divide(match_dist, norm_dist).astype(fs_dtype)
    fx2_to_isvalid = np.less(fx2_to_ratio, ratio_thresh)
    fm_RAT = fm.compress(fx2_to_isvalid, axis=0).astype(fm_dtype)
    fx1_norm_RAT = fx1_norm.compress(fx2_to_isvalid).astype(fm_dtype)
    # Turn the ratio into a score
    fs_RAT = np.subtract(1.0, fx2_to_ratio.compress(fx2_to_isvalid))
    # return normalizer info as well
    fm_norm_RAT = np.vstack((fx1_norm_RAT, fm_RAT.T[1])).T
    ratio_tup = MatchTup3(fm_RAT, fs_RAT, fm_norm_RAT)
    return ratio_tup


def ensure_fsv_list(fsv_list):
    """ ensure fs is at least Nx1 """
    return [fsv[:, None] if len(fsv.shape) == 1 else fsv
            for fsv in fsv_list]


def marge_matches(fm_A, fm_B, fsv_A, fsv_B):
    """ combines feature matches from two matching algorithms

    Args:
        fm_A (ndarray[ndims=2]): type A feature matches
        fm_B (ndarray[ndims=2]): type B feature matches
        fsv_A (ndarray[ndims=2]): type A feature scores
        fsv_B (ndarray[ndims=2]): type B feature scores

    Returns:
        tuple: (fm_both, fs_both)

    CommandLine:
        python -m vtool.matching --test-marge_matches

    Example:
        >>> # ENABLE_DOCTEST
        >>> from vtool.matching import *  # NOQA
        >>> fm_A  = np.array([[ 15, 17], [ 54, 29], [ 95, 111], [ 25, 125], [ 97, 125]], dtype=np.int32)
        >>> fm_B  = np.array([[ 11, 21], [ 15, 17], [ 25, 125], [ 30,  32]], dtype=np.int32)
        >>> fsv_A = np.array([[ .1, .2], [1.0, .9], [.8,  .2],  [.1, .1], [1.0, .9]], dtype=np.float32)
        >>> fsv_B = np.array([[.12], [.3], [.5], [.7]], dtype=np.float32)
        >>> # execute function
        >>> (fm_both, fs_both) = marge_matches(fm_A, fm_B, fsv_A, fsv_B)
        >>> # verify results
        >>> result = ut.list_str((fm_both, fs_both), precision=3)
        >>> print(result)
        (
            np.array([[ 15,  17],
                      [ 25, 125],
                      [ 54,  29],
                      [ 95, 111],
                      [ 97, 125],
                      [ 11,  21],
                      [ 30,  32]], dtype=np.int32),
            np.array([[ 0.1 ,  0.2 ,  0.3 ],
                      [ 0.1 ,  0.1 ,  0.5 ],
                      [ 1.  ,  0.9 ,   nan],
                      [ 0.8 ,  0.2 ,   nan],
                      [ 1.  ,  0.9 ,   nan],
                      [  nan,   nan,  0.12],
                      [  nan,   nan,  0.7 ]], dtype=np.float64),
        )
    """
    # Flag rows found in both fmA and fmB
    # that are intersecting (both) or unique (only)
    import vtool as vt
    flags_both_A, flags_both_B = vt.intersect2d_flags(fm_A, fm_B)
    flags_only_A = np.logical_not(flags_both_A)
    flags_only_B = np.logical_not(flags_both_B)
    # independent matches
    fm_both_AB  = fm_A.compress(flags_both_A, axis=0)
    fm_only_A   = fm_A.compress(flags_only_A, axis=0)
    fm_only_B   = fm_B.compress(flags_only_B, axis=0)
    # independent scores
    fsv_both_A = fsv_A.compress(flags_both_A, axis=0)
    fsv_both_B = fsv_B.compress(flags_both_B, axis=0)
    fsv_only_A = fsv_A.compress(flags_only_A, axis=0)
    fsv_only_B = fsv_B.compress(flags_only_B, axis=0)
    # build merge offsets
    offset1 = len(fm_both_AB)
    offset2 = offset1 + len(fm_only_A)
    offset3 = offset2 + len(fm_only_B)
    # Merge feature matches
    fm_merged = np.vstack([fm_both_AB, fm_only_A, fm_only_B])
    # Merge feature scores
    num_rows = fm_merged.shape[0]
    num_cols_A = fsv_A.shape[1]
    num_cols_B = fsv_B.shape[1]
    num_cols = num_cols_A + num_cols_B
    fsv_merged = np.full((num_rows, num_cols), np.nan)
    fsv_merged[0:offset1, 0:num_cols_A] = fsv_both_A
    fsv_merged[0:offset1, num_cols_A:]  = fsv_both_B
    fsv_merged[offset1:offset2, 0:num_cols_A] = fsv_only_A
    fsv_merged[offset2:offset3, num_cols_A:]  = fsv_only_B
    return fm_merged, fsv_merged


if __name__ == '__main__':
    """
    CommandLine:
        python -m vtool.matching
        python -m vtool.matching --allexamples
        python -m vtool.matching --allexamples --noface --nosrc
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
