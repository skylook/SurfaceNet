import numpy as np
import os
import math
import scipy.io

## define the parameters that don't vary in the main function, such as the patch size and the cube size.
## for the parameters that may change in the different main loop through different models in a dataset, we load them use the function `load_modelSpecific_params` defined at the end of this file.

# "reconstruct_model"
whatUWant = "train_model"

__datasetName = 'Middlebury'  # Middlebury / DTU, only set the dataset for reconstruction
__GPUMemoryGB = 12  # how large is your GPU memory (GB)
__input_data_rootFld = "./inputs"
__output_data_rootFld = "./outputs"


###########################
#   several modes:
#   "train_xxx" "reconstruct_model"
###########################
__DEBUG_input_data_rootFld = "/home/mengqi/fileserver/datasets"     # used for debug: if exists, use this path
__DEBUG_output_data_rootFld = "/home/mengqi/fileserver/results/MVS/SurfaceNet"
__DEBUG_input_data_rootFld_exists = os.path.exists(__DEBUG_input_data_rootFld)
__DEBUG_output_data_rootFld_exists = os.path.exists(__DEBUG_output_data_rootFld)
__input_data_rootFld = __DEBUG_input_data_rootFld if __DEBUG_input_data_rootFld_exists else __input_data_rootFld
__output_data_rootFld = __DEBUG_output_data_rootFld if __DEBUG_output_data_rootFld_exists else __output_data_rootFld

debug_BB = False


if whatUWant is "reconstruct_model": 
    """
    In this mode, reconstruct models using the similarityNet and SurfaceNet.
    """
    #------------ 
    ## params only for reconstruction
    #------------
    # DTU: numbers: 1 .. 128
    # Middlebury: dinoSparseRing
    if __datasetName is 'DTU':
        __modelList = [9]     # [3,18,..]
    elif __datasetName is 'Middlebury':
        __modelList = ["dinoSparseRing"]     # ["dinoSparseRing", "..."]

    __cube_D = 64 #32/64 # size of the CVC = __cube_D ^3, in the paper it is (s,s,s)
    __min_prob = 0.46 # in order to save memory, filter out the voxels with prob < min_prob
    __tau = 0.7     # fix threshold for thinning
    __gamma = 0.8   # used in the ray pooling procedure

    # TODO tune, gpuarray.preallocate=0.95 / -1 
    __batchSize_similNet_patch2embedding_perGB = 350
    __batchSize_similNet_embeddingPair2simil_perGB = 100000
    __batchSize_viewPair_w_perGB = 100000     


    __batchSize_similNet_patch2embedding, __batchSize_similNet_embeddingPair2simil, __batchSize_viewPair_w = np.array([\
            __batchSize_similNet_patch2embedding_perGB, \
            __batchSize_similNet_embeddingPair2simil_perGB, \
            __batchSize_viewPair_w_perGB, \
            ], dtype=np.uint64) * __GPUMemoryGB

    ############# 
    ## similarNet
    #############

    # each patch pair --> features to learn to decide view pairs
    # 2 * 128D/image patch + 1 * (dis)similarity + 1 * angle<v1,v2>
    __D_imgPatchEmbedding = 128
    __D_viewPairFeature = __D_imgPatchEmbedding * 2 + 1 + 1     # embedding / view pair angle / similarity
    __similNet_hidden_dim = 100
    __pretrained_similNet_model_file = os.path.join(__input_data_rootFld, 'SurfaceNet_models/epoch33_acc_tr0.707_val0.791.model') # allDTU
    __imgPatch_hw_size = 64
    __MEAN_IMAGE_BGR = np.asarray([103.939,  116.779,  123.68]).astype(np.float32)
    __triplet_alpha = 100
    __weight_decay = 0.0001
    __DEFAULT_LR = 0 # will be updated during param tuning

    ############
    # SurfaceNet
    ############

    # view index of the considered views
    __use_pretrained_model = True
    if __use_pretrained_model:
        __layerNameList_2_load = ["output_SurfaceNet_reshape","output_softmaxWeights"] ##output_fusionNet/fuse_op_reshape
        __pretrained_SurfaceNet_model_file = os.path.join(__input_data_rootFld, 'SurfaceNet_models/2D_2_3D-19-0.918_0.951.model') # allDTU
    __cube_Dcenter = {32:26, 64:52}[__cube_D] # only keep the center part of the cube because of boundary effect of the convNet.

    ####################
    # adaptive threshold
    ####################
    __beta = 6
    __N_refine_iter = 8
    __cube_overlapping_ratio = 1/2. ## how large area is covered by the neighboring cubes. 
    __weighted_fusion = True # True: weighted average in the fusion layer; False: average

    __batchSize_nViewPair_SurfaceNet_perGB = {32:1.2, 64:0.1667}[__cube_D]  # 0.1667 = 1./6
    __batchSize_nViewPair_SurfaceNet = int(math.floor(__batchSize_nViewPair_SurfaceNet_perGB * __GPUMemoryGB))
  


elif whatUWant is "train_model":

    __datasetName = 'DTU'  # DTU
    __modelList_train = [2,6] # [2, 6, 7, 8, 14, 16, 18, 19, 20, 22, 30, 31, 36, 39, 41, 42, 44, \
            # 45, 46, 47, 50, 51, 52, 53, 55, 57, 58, 60, 61, 63, 64, 65, 68, 69, 70, 71, 72, \
            # 74, 76, 83, 84, 85, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, \
            # 101, 102, 103, 104, 105, 107, 108, 109, 111, 112, 113, 115, 116, 119, 120, \
            # 121, 122, 123, 124, 125, 126, 127, 128]
    __modelList_val = [3,5]  # [3, 5, 17, 21, 28, 35, 37, 38, 40, 43, 56, 59, 66, 67, 82, 86, 106, 117]     # validation
    __layer_2_load_model = ["output_volumeNet"] # ["output_volumeNet_reshape","output_softmaxWeights"]#"output_volumeNet" ##output_fusionNet/fuse_op_reshape
    __lightConditions = ['3_r5000']  # ['{}_r5000'.format(_) for _ in range(7)] + ['max']   # hard to load all the imgs to memory
    imgNamePattern_fn = lambda _model, _light: "Rectified/scan{}/rect_#_{}.png".format(_model, _light)    # replace # to {:03} 
    __datasetFolder = os.path.join(__input_data_rootFld, 'DTU_MVS')
    __poseNamePattern = "SampleSet/MVS Data/Calibration/cal18/pos_#.txt"  # replace # to {:03}
    __modelFile_pattern = "Points/stl/stl#_total.ply"
    __npzFile_pattern = "surfacePts/DTU/model#.npz" # TODO:
    __soft_label = False
    __cube_D = 32 # size of the CVC = __cube_D ^3, in the paper it is (s,s,s)
    __chunk_len_train = 6
    __N_viewPairs4train = 6
    __N_epochs = 1000
    __viewList = range(1,50)  # only use the first 49 views for training

###########################
#   params rarely change
###########################
__MEAN_CVC_RGBRGB = np.asarray([123.68,  116.779,  103.939, 123.68,  116.779,  103.939]).astype(np.float32) # RGBRGB order (VGG mean)
__MEAN_PATCHES_BGR = np.asarray([103.939,  116.779,  123.68]).astype(np.float32)




## print the params in log
for _var in dir():
    if '__' in _var and not (_var[-2:] == '__'): # don't show the uncustomed variables, like '__builtins__'
        exec("print '{} = '.format(_var), "+_var)



def load_modelSpecific_params(datasetName, model):
    """
    In order to loop through the different models in a same dataset.
    This function only assign different params associated with different model in each reconstrction loop.
    ----------
    inputs:
        datasetName: such as "DTU" / "Middlebury" ... 
        model: such as 3 / "dinoSparseRing" / ...
    outputs:
        datasetFolder: root folder of this dataset
        imgNamePattern: pattern of the img path, replace # to view index
        poseNamePattern: 
        N_viewPairs4inference: how many viewPairs used for reconstruction
        resol: size of voxel
        BB: Bounding Box of this scene.  np(2,3) float32
        viewList: which views are used for reconstruction.
    """

    if datasetName is "DTU":
        datasetFolder = os.path.join(__input_data_rootFld, 'DTU_MVS')
        imgNamePattern = "Rectified/scan{}/rect_#_3_r5000.{}".format(model, 'png' if __DEBUG_input_data_rootFld_exists else 'jpg')    # replace # to {:03} 
        poseNamePattern = "SampleSet/MVS Data/Calibration/cal18/pos_#.txt"  # replace # to {:03}
        N_viewPairs4inference = [5]
        resol = np.float32(0.4) #0.4 resolution / the distance between adjacent voxels
        BBNamePattern = "SampleSet/MVS Data/ObsMask/ObsMask{}_10.mat".format(model)
        BB_filePath = os.path.join(datasetFolder, BBNamePattern)
        BB_matlab_var = scipy.io.loadmat(BB_filePath)   # matlab variable
        reconstr_sceneRange = [(0, 60), (-150, -100), (580, 630)]
        BB = reconstr_sceneRange if debug_BB else BB_matlab_var['BB']   # np(2,3)
        BB = BB.T   # (3,2)
        viewList = range(1,50)  # range(1,50)

    if datasetName is "Middlebury":
        datasetFolder = os.path.join(__input_data_rootFld, 'Middlebury')
        N_viewPairs4inference = [3]
        resol = np.float32(0.00025) # 0.00025 resolution / the distance between adjacent voxels
        if model is "dinoSparseRing":
            imgNamePattern = "{}/dinoSR0#.png".format(model)   # replace # to {:03}
            poseNamePattern = "{}/dinoSR_par.txt".format(model)
            BB = [(-0.061897, 0.010897), (-0.018874, 0.068227), (-0.057845, 0.015495)]
            viewList = range(7,13) #range(1,16)
        else:
            raise Warning('current model is unexpected: '+model+'.') 
    return datasetFolder, imgNamePattern, poseNamePattern, N_viewPairs4inference, resol, np.array(BB, dtype=np.float32), viewList


