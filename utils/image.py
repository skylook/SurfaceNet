import scipy.misc
import scipy.ndimage
import os
import math
import random
random.seed(201801)
import numpy as np
np.random.seed(201801)



def preprocess_patches(patches, mean_BGR):
    """
    (h,w,c) --> (c,h,w); RGB --> BGR; minuse mean_BGR along coler channel.

    ------------
    inputs:
        patches: np (...,h,w,c) in the RGB order
        mean_BGR: np (3/1,)

    ------------
    outputs:
        patches: np (...,c,h,w) in the BGR order. Processed patches.

    ------------
    usages:
    >>> patches = preprocess_patches(np.zeros((2,2,5,3)), mean_BGR=np.array([1,2,3]))
    >>> patches# doctest: +ELLIPSIS, +NORMALIZE_WHITESPACE
    array([[[[-1., -1., -1., -1., -1.],
             [-1., -1., -1., -1., -1.]],
    <BLANKLINE>
            [[-2., -2., -2., -2., -2.],
             [-2., -2., -2., -2., -2.]],
    <BLANKLINE>
            [[-3., -3., -3., -3., -3.],
             [-3., -3., -3., -3., -3.]]],
    ...
    >>> patches = preprocess_patches(np.zeros((2,1,2,5,1)), mean_BGR=np.array([2]))
    >>> patches.shape
    (2, 1, 1, 2, 5)
    >>> patches[0]   # doctest: +ELLIPSIS, +NORMALIZE_WHITESPACE
    array([[[[-2., -2., -2., -2., -2.],
             [-2., -2., -2., -2., -2.]]]])
    """

    # patches = np.transpose(patches, (0,3,1,2)) # (...,h,w,c) ==> (...,c,h,w)
    patches = np.moveaxis(patches, -1, -3)    # (...,h,w,c) ==> (...,c,h,w)
    patches = patches[..., ::-1, :, :] # RGB ==> BGR
    patches -= mean_BGR[:, None, None]  # operate if the trailing axes are the same
    return patches


def readImages(datasetFolder, imgNamePattern, viewList, return_list = True, silentLog = False):
    """
    Only select the images of the views listed in the viewList.
    We assume that the view index is large or equal than 0
        &&
        the images' sizes are equal.

    Note that the size of the images may be different.

    ---------
    inputs:
        datasetFolder: where the dataset locates
        imgNamePattern: different dataset have different name patterns for images. Remember to include the subdirecteries, e.g. "x/x/xx.png"
        viewList: list the view index, such as [11, 1, 30, 6]
        return_list: True.  Return list if true else np.

    ---------
    outputs:
        imgs_list: list of the images
            or
        imgs_np: np array with shape of (len(viewList), img_h, img_w, 3)

    ---------
    usages:
    >>> imgs_np = readImages(".", "test/Lasagne0#.jpg", [6,6], return_list = False)     # doctest need to run in the local dir
    loaded img ./test/Lasagne0006.jpg
    loaded img ./test/Lasagne0006.jpg
    >>> imgs_np.shape
    (2, 225, 225, 3)
    >>> imgs_np[:, 0, 0]
    array([[216, 228, 240],
           [216, 228, 240]], dtype=uint8)
    """

    if return_list:
        imgs_list = []

        for i, viewIndx in enumerate(viewList):
            imgPath = os.path.join(datasetFolder, imgNamePattern.replace('#', '{:03}'.format(viewIndx)))  # we assume the name pattern looks like 'x/x/*001*.xxx', if {:04}, add one 0 in the pattern: '*0#*.xxx'
            img = scipy.misc.imread(imgPath)    # read as np array
            imgs_list.append(img)
            if not silentLog:
                print('loaded img ' + imgPath)
        
        return imgs_list 
    else:
        imgs_np = None
        for i, viewIndx in enumerate(viewList):
            imgPath = os.path.join(datasetFolder, imgNamePattern.replace('#', '{:03}'.format(viewIndx)))  # we assume the name pattern looks like 'x/x/*001*.xxx', if {:04}, add one 0 in the pattern: '*0#*.xxx'
            img = scipy.misc.imread(imgPath)    # read as np array
            if i == 0:
                imgs_np = np.zeros((len(viewList), ) + img.shape).astype(img.dtype)
            imgs_np[i] = img
            if not silentLog:
                print('loaded img ' + imgPath)
        return imgs_np

def readImages_models_views_lights(datasetFolder, modelList, viewList, lightConditions, imgNamePattern_fn, 
        random_lightCondition = False, silentLog = False):
    """
    Assume the images taken for the same model have the same shape.
    Return list loop through models with each element = np.array (N_views, N_lights, h, w, 3/1)
    
    inputs:
    ------- 
    random_lightCondition: if True: select one image with random light condition
            if False: select the images from all the listed light conditions

    outputs:
    --------
    record_lastLightCondition4models: used to print log, match the randomness. So that few of them are enough.
    """

    images4models_list = [None for _model in modelList]
    record_lastLightCondition4models = []
    for _i, _model in enumerate(modelList):
        images4lights = None
        if random_lightCondition:  # load model's view imgs with different light conditions
            for _j, _view in enumerate(viewList):
                _light = random.sample(lightConditions, 1)[0]
                images4view = readImages(datasetFolder = datasetFolder, imgNamePattern = imgNamePattern_fn(_model, _light), \
                        viewList = viewList[_j: _j+1], return_list = False, silentLog = silentLog) # (1, H, W, 3)
                if _j == 0:
                    images4lights = np.zeros((len(viewList), 1) + tuple(images4view.shape[-3:])).astype(images4view.dtype)
                images4lights[_j] = images4view
        else:   # load model's view images with the same light condition
            for _j, _light in enumerate(lightConditions):
                images4views = readImages(datasetFolder = datasetFolder, imgNamePattern = imgNamePattern_fn(_model, _light), \
                        viewList = viewList, return_list = False, silentLog = silentLog) # (N_views, H, W, 3)
                if _j == 0:
                    images4lights = np.zeros((len(viewList), len(lightConditions)) + tuple(images4views.shape[-3:])).astype(images4views.dtype)
                images4lights[:, _j] = images4views

        record_lastLightCondition4models.append(_light)
        images4models_list[_i] = images4lights
    return images4models_list, record_lastLightCondition4models


def cropImgPatches(img, range_h, range_w, patchSize = 64, pyramidRate = 1.2, interp_order = 2):
    """
    crop patches from a specific image. Up/down sample the image according to the img_h/w of the projected region.
    N_pyramid = NO. of the image pyramid layers 
    When N_pyramid = 1, it means that only crop the squared patch (with size = patchSize)  from the input image without up/down sampling.
    When N_pyramid > 1, up/down sampling will be used to crop patches. 
    When N_pyramid --> Inf, approximately, this operation is nothing but the one that the projected region will be resized to a patch with size = patchSize. Since resize all the projection region is time comsuming, we use small N_pyramid to approximate this operation.

    If pyramidRate == 1, there are infinite pyramid layers. In this case we only set one img in the pyramid.

    ------------
    inputs:
        img: the input image with any shape, (h,w,3/1)
        range_h: (N_patches, 2), 2 columns [min, max] pixel range. For outrange h(h < 0)=0; h(h > h_max)=h_max.
        range_w: ... 
        patchSize = 64: size of the cropped squared patch.
        pyramidRate = 1.2: sampling rate between the adjacent pyramid layers.
        interp_order: The order of the spline interpolation, default is 3. The order has to be in the range 0-5.
                When scipy.ndimage.interpolation.zoom order = 0: can be used in the doctest

    ------------
    outputs:
        patches: (N_patches, patchSize, patchSize, 3/1)

    ------------
    usages:
    >>> imgs_np = readImages(".", "test/Lasagne0#.jpg", [6], return_list = False) 
    loaded img ./test/Lasagne0006.jpg
    >>> imgs_np.shape
    (1, 225, 225, 3)
    >>> range_h = np.array([[115,90,115,20], [125, 150, 125, 220]]).T     # (4,2), center_h = 120
    >>> range_w = np.array([[110,115,70,115], [130,125,170,125]]).T    # (4,2), center_w = 120
    >>> img = imgs_np[0]
    >>> hw = img.shape[0]
    >>> patches = cropImgPatches(img = img, range_h = range_h, range_w = range_w, patchSize = 64, pyramidRate = 2, interp_order = 0)
    >>> patches.shape
    (4, 64, 64, 3)
    >>> # np.any(np.diff(patches, axis=0))    # (4,64,64,3) --> (3,64,64,3), all zeros
    >>> np.allclose(patches[0,32,32,:], patches[1,32,32,:])     # the center pixel equals
    True
    >>> img_2 = np.repeat(np.repeat(img, 2, axis=0), 2, axis=1)
    >>> np.allclose(patches[0], img_2[240-32:240+32, 208:272])
    True
    >>> np.allclose(patches[1], img[120-32:120+32, 88:152])
    True
    >>> np.array_equiv(patches[2,32,32,:], img[120,120])   # 2x downsample. equals the center pixel
    True
    >>> np.array_equiv(patches[3,32,32,:], img[122,122])   # 4x downsample. equals the center pixel
    True
    >>> patches_identical = cropImgPatches(img = img, range_h = range_h, range_w = range_w, patchSize = 64, pyramidRate = 1, interp_order = 0)  # there is ONE image in the pyramid when pyramidRate=1
    >>> np.allclose(patches_identical[0], patches_identical[1])
    True
    >>> np.allclose(patches_identical[1], patches_identical[2])
    True
    >>> np.allclose(patches_identical[2], patches_identical[3])
    True
    
    # out of range indexing:
    >>> img += np.random.randint(0, 128, img.shape).astype(np.uint8) # easy to check
    >>> range_h = np.array([[-2], [10]]).T     # center_h = 4
    >>> range_w = np.array([[-6], [0]]).T    # center_w = -3
    >>> patches = cropImgPatches(img = img, range_h = range_h, range_w = range_w, patchSize = 10, pyramidRate = 1, interp_order = 2)  # can print out patches to check
    >>> np.array_equal(patches[0, 1:9, 0, 0], img[0:8, 0, 0])
    True
    """

    N_patches = range_h.shape[0]
    patchSize_r = patchSize / 2
    # get patch center in the original image.
    center_h = np.mean(range_h, axis=1) # (N_patches,)
    center_w = np.mean(range_w, axis=1)

    img_h, img_w, img_c = img.shape
    img_dtype = img.dtype

    range_hw_max = np.maximum(range_h[:,1] - range_h[:,0], range_w[:,1] - range_w[:,0])   # elementwise maximum. (N_patches,). The longest projection on the axes. If small, upsample the image in order to crop a fixed size patch.

    # determine how many layers of the image pyramid
    patchSizeRatio = float(patchSize) / range_hw_max     # (N_patches,)
    logRatio = (np.log(patchSizeRatio) / np.log(pyramidRate)) if pyramidRate is not 1 else np.ones(patchSizeRatio.shape)     # element-wise log, if pyramidRate == 1, there are infinite pyramid layers. In this case we only set one img in the pyramid.
    logRatio_int = np.floor(logRatio)  # -1.2 --> -2; 3.7 --> 3

    patches = np.empty((N_patches, patchSize, patchSize, img_c), dtype=img_dtype)
    N_pyramid = len(set(logRatio_int))   # how many layers of the image pyramid
    if N_pyramid > 10:
        print("Warning: there are so many layers ({}) in the pyramid that it may be expensive".format(N_pyramid))

    for _logRatio_int in set(logRatio_int):
        _resizeRate = pyramidRate ** _logRatio_int 
        _imgResize = scipy.ndimage.interpolation.zoom(input = img, zoom = (_resizeRate, _resizeRate, 1.), output=img_dtype, order=interp_order)       # (img_h*_resizeRate, img_w*_resizeRate, 3/1)
        _imgResize_h, _imgResize_w = _imgResize.shape[:2]
        # because we want to use numpy indexing (fast). For example img[[[2,2],[3,3]], [[7,8],[7,8]]] accesses 4 pixels and forms an array with shape (2,2):
        # [pixel[2,7],pixel[2,8]
        #  pixel[3,7],pixel[3,8]]
        # The accessed pixels should not be out of range of the image boundary. 
        # (unlike PIL, (goodness) which just leave the outside pixel as 0, (drawback) but takes long time) 
        _select = (logRatio_int == _logRatio_int) # (N_patches,) select perticular _logRatio_int
        _patch_h_min = (center_h[_select] * _resizeRate).astype(np.int) - patchSize_r    # (N_logRatioInt, ) 
        _patch_w_min = (center_w[_select] * _resizeRate).astype(np.int) - patchSize_r    
        _patch_h_max = _patch_h_min + patchSize
        _patch_w_max = _patch_w_min + patchSize
        _patchRelativeCoords = np.indices((patchSize, patchSize))    # (2,patchSize,patchSize)
        _pixel_h = np.clip(_patch_h_min[:,None,None] + _patchRelativeCoords[0:1], a_min=0, a_max=_imgResize_h-1)      # (N_logRatioInt, 1, 1) + (1, patchSize, patchSize) --> (N_logRatioInt, patchSize, patchSize), clip to range [0, _imgResize_h) for indexing
        _pixel_w = np.clip(_patch_w_min[:,None,None] + _patchRelativeCoords[1:2], a_min=0, a_max=_imgResize_w-1)

        patches[_select] = _imgResize[_pixel_h, _pixel_w, :]      # (N_patches, patchSize, patchSize, 3/1), indexing all the pixels in multiple patches at one time.  _pixel_h/w much be integer.

    return patches


def img_hw_cubesCorner_inScopeCheck(hw_shape, img_h_cubesCorner, img_w_cubesCorner):
    """
    img_h/w_cubesCorner is the projection coords of the cubes corners.
    inputs: 
    # (N_cubes,) inScope check and select perticular _logRatio_int. 

    -----------
    inputs:
        hw_shape: (h_int, w_int)
        img_h_cubesCorner: (N_cubes, 8)
        img_w_cubesCorner: (N_cubes, 8)
    """
    img_h, img_w = hw_shape
    range_h_min = np.min(img_h_cubesCorner, axis=1)    # (N_cubes, 8) --> (N_cubes,)
    range_h_max = np.max(img_h_cubesCorner, axis=1)
    range_w_min = np.min(img_w_cubesCorner, axis=1)
    range_w_max = np.max(img_w_cubesCorner, axis=1)
    inScope = (range_h_min >= 0) & (range_h_max <= img_h) & (range_w_min >= 0) & (range_w_max <= img_w) # (N_cubes,) inScope check and select perticular _logRatio_int. 
    return inScope



import doctest
doctest.testmod()
