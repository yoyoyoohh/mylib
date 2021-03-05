''' last modefied: 2021-01-23 '''
import os
from shutil import Error
import sys
import cv2
import PIL.Image
from matplotlib.pyplot import contour
import numpy as np
from typing import Union
import itertools
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import imgviz
import pandas as pd
import os.path as osp
import json
import base64
import labelme.utils
import warnings

''' usage: 
        1) run check_label_name()
        2) run json_to_dataset_batch()
        3) run generate_and_get_label_statistics()
        4) run get_label_statistics()
'''

def get_corrds_from_slice_idx(img_shape:Union[tuple, list, np.ndarray], patch_shape:Union[tuple,list, np.ndarray], slice_idx:Union[str, int]):
    ''' get the coordinates of the up left corner of the patch in a big image
    @in     -img_shape      -shape of the big image, in [height, width] format
            -patch_shape    -shape of the patch, in [height, width] format
            -slice_idx      -index of the patch, starts from 0
    @ret    -coords         -coordinates of the up left corner of the patch 
    '''
    # check
    if isinstance(slice_idx, str):
        slice_idx = int(slice_idx)
    img_het = img_shape[0]
    img_wes = img_shape[1]
    if (img_het<patch_shape[0]) or (img_wes<patch_shape[1]):
        raise ValueError('shape of image must greater than the patch')

    # calculate
    patches_per_row = (img_wes-1) // patch_shape[1] + 1
    [rows, cols] = divmod(slice_idx, patches_per_row)
    coords = np.zeros(2)
    coords[0] = patch_shape[0]*rows
    coords[1] = patch_shape[1]*cols

    # correct if the patch exceeds the bottom or right boundary
    if coords[0]>img_het-patch_shape[0]:
        coords[0] = img_het-patch_shape[0]
    if coords[1]>img_wes-patch_shape[1]:
        coords[1] = img_wes-patch_shape[1]
    return coords.astype(np.int32)

def lblsave(filename:str, lbl:np.ndarray, colormap:np.ndarray = None):
    ''' save label file as an image with visible colors
    download from https://github.com/wkentaro/labelme/blob/master/labelme/utils/_io.py, 
    @in     -filename       -file name to be save as
            -lbl            -label file, in 2D format
            -colormap       -colormap, Nx3 format
    '''

    if os.path.splitext(filename)[1] != ".png":
        filename += ".png"
    # Assume label ranses [-1, 254] for int32,
    # and [0, 255] for uint8 as VOC.
    if lbl.min() >= -1 and lbl.max() < 255:
        lbl_pil = PIL.Image.fromarray(lbl.astype(np.uint8), mode="P")
        clrmap = imgviz.label_colormap().flatten()
        if colormap is not None:
            clrmap[0:colormap.size] = colormap.flatten()
            # colormap = np.pad(colormap, (0, 768-colormap.size), mode='constant')
        # print(clrmap.size)
        # print(np.unique(lbl))
        
        lbl_pil.putpalette(clrmap)
        lbl_pil.save(filename)
    else:
        raise ValueError(
            "[%s] Cannot save the pixel-wise class label as PNG. "
            "Please consider using the .npy format." % filename
        )


def my_json2dataset(json_file, lbl_names_all):
    ''' modified from labelme's json_to_dataset.py, 
    相比于原来的按照图中的标注来对label数字进行排序的方法，我直接指定了全部的label名称及其数字，这样的话所有标注的文件会统一，但是也只能适用于这个单一任务 
    @in     -json_file      -json文件
            -lbl_names_all  -所有的label的名称
    '''
    print(f'processing:{json_file}', end='')
    out_dir = osp.basename(json_file).replace(".", "_")
    out_dir = osp.join(osp.dirname(json_file), out_dir)
  
    if not osp.exists(out_dir):
        os.mkdir(out_dir)

    data = json.load(open(json_file))
    imageData = data.get("imageData")

    if not imageData:
        imagePath = os.path.join(os.path.dirname(json_file), data["imagePath"])
        with open(imagePath, "rb") as f:
            imageData = f.read()
            imageData = base64.b64encode(imageData).decode("utf-8")
    img = labelme.utils.img_b64_to_arr(imageData)

    # 将这段被注释的代码改为下面那段
    # label_name_to_value = {"_background_": 0}
    # for shape in sorted(data["shapes"], key=lambda x: x["label"]):
    #     label_name = shape["label"]
    #     if label_name in label_name_to_value:
    #         label_value = label_name_to_value[label_name]
    #     else:
    #         label_value = len(label_name_to_value)
    #         label_name_to_value[label_name] = label_value
    label_name_to_value = {}
    for label_value, label_name in enumerate(lbl_names_all):
        label_name_to_value[label_name] = label_value

    lbl, _ = labelme.utils.shapes_to_label(
        img.shape, data["shapes"], label_name_to_value
    )

    label_names = [None] * (max(label_name_to_value.values()) + 1)
    for name, value in label_name_to_value.items():
        label_names[value] = name

    lbl_viz = imgviz.label2rgb(
        label=lbl, img=imgviz.asgray(img), label_names=label_names, loc="rb"
    )

    PIL.Image.fromarray(img).save(osp.join(out_dir, "img.png"))
    labelme.utils.lblsave(osp.join(out_dir, "label.png"), lbl)
    PIL.Image.fromarray(lbl_viz).save(osp.join(out_dir, "label_viz.png"))

    with open(osp.join(out_dir, "label_names.txt"), "w") as f:
        for lbl_name in label_names:
            f.write(lbl_name + "\n")

    print('  done')
    # print("Saved to: {}".format(out_dir))


def json_to_dataset_batch(src_path:str, lbl_names_all):
    ''' 批量将指定文件夹中所有的 labelme 产生的 .json 文件转为适合处理的图像文件
        @in     -src_path   -labelme标注后的.json文件存放的路径
    '''
    for dirpath, sub_dirs, files in os.walk(src_path):
        for file in files:
            if '.json' in file:
                # 这是用原来的 labelme 提供的 exe 文件进行处理
                # cmd = 'labelme_json_to_dataset ' + os.path.join(dirpath, file)
                # print('excuting ', cmd)
                # os.system(cmd)

                # 用我修改后的代码进行处理
                my_json2dataset(osp.join(dirpath, file), lbl_names_all)
    print('finished')


def read_change_label_png(src_path:str)->np.ndarray:
    ''' 读取表示变化检测的的label的png文件，这个文件的格式比较复杂，直接读取会有问题，需要特殊处理
    @in     -src_path       -指向 label.png 的路径
    @ret    -label_idx      -np.ndarray格式的label信息,其中0表示信息确实，1表示无变化，2表示存在变化
    '''
    if src_path[-4:] != r'.png':
        raise ValueError('Not a png file')
    tmp = PIL.Image.open(src_path)
    label_idx = np.asarray(tmp)
    return label_idx


def read_label_png(src_path:str)->np.ndarray:
    '''读取 label.png 包含的label信息，这个文件的格式比较复杂，直接读取会有问题，需要特殊处理
    @in     -src_path       -label.png 所在文件夹或者 指向 label.png 的路径
    @ret    -label_idx      -np.ndarray格式的label信息
            -label_name     - tuple 格式的label名字，对应 label_idx里面的索引
    '''
    # read label.png, get the label index
    if src_path[-10:] != r'/label.png' and src_path[-10:] != r'\label.png':
        src_path = os.path.join(src_path, 'label.png')
    tmp = PIL.Image.open(src_path)
    label_idx = np.asarray(tmp)

    # read label_names.txt, get the label class names corresponding to label index
    label_name = []
    with open(src_path.replace('label.png', 'label_names.txt')) as txt:
        for line in txt:
            label_name.append(line.strip())
    # print(label.dtype)
    # print(np.unique(label))
    # print(label.shape)
    return (label_idx, tuple(label_name))


# def compare_sematic_label()

def reconstrcut_label(lbl_idx:np.ndarray, lbl_name:Union[list, tuple], lbl_name_all:Union[list, tuple]):
    ''' recontruct the label so that same index indicated same class 
    @in     -lbl_idx        -old label index
            -lbl_name       -old label_name associated to lbl_idx
            -lbl_name_all   -label names to which the new label index is reconstructed
    @out    -lbl_idx_new    -reconstructed label index
    '''
    # check
    if not set(lbl_name).issubset(lbl_name_all):
        raise ValueError('unknown label name')

    # reconstrcut the label index matrix
    else:   
        lbl_idx_new = lbl_idx.copy()
        for cnt, cls in enumerate(lbl_name):
            pos = lbl_name_all.index(cls)
            if cnt != pos:
                lbl_idx_new[lbl_idx==cnt] = pos
    
    return lbl_idx_new


def mask_label(lbl_idx:np.ndarray, lbl_name_all:Union[list, tuple], change_name:Union[list, tuple]):
    ''' mask a label class to be another label class, this is task-specific
    @in     -lbl_idx        -label index matrix
            -lbl_name_all   -label names
            -change_name    - (the original class, the target class)
    @ret    -lbl_idx_new    -new label matrix
    '''
    original_idx = lbl_name_all.index(change_name[0])
    new_idx = lbl_name_all.index(change_name[1])
    lbl_idx_new = lbl_idx.copy()
    lbl_idx_new[lbl_idx==original_idx] = new_idx
    return lbl_idx_new


def get_label_statistics(src_path:str, label_names_all:Union[list, tuple]):
    ''' 统计由 labelme 产生的语义分割标注文件的语义统计信息
        @in     -src_path       -标注文件存放的路径
        @ret    -cls_cnt        -不同类别对应的像素数量
                -change_cnt     -变化的像素数量和总的像素数量
    '''
    cls_cnt = np.zeros(len(label_names_all), dtype=np.uint32)
    change_cnt = np.zeros(2, dtype=np.uint32)

    for dirpath, sub_dirs, files in os.walk(src_path):
        if 'label.png' in files:           # semantic labels
            lbl_idx, lbl_name = read_label_png(os.path.join(dirpath, 'label.png'))
            lbl_idx = reconstrcut_label(lbl_idx, lbl_name, label_names_all)
            hist, _ = np.histogram(lbl_idx, range(len(label_names_all)+1))
            cls_cnt += hist.astype(np.uint32)
    
        for file in files:              # chagne detection labels
            if '-change' in file:
                lbl_idx = read_change_label_png(osp.join(dirpath, file))
                change_cnt[0] += (lbl_idx==2).sum()
                change_cnt[1] += 512**2

    return cls_cnt, change_cnt


def generate_change_label(src_path:str, label_names_all:Union[list, tuple]):
    ''' 生成变化检测的label, label中黑色表示没有变化，白色表示存在变化，灰色表示没有标注，然后统计变化的像素，变化检测的label中 0 表示没有标注, 1 表示无变化, 2 表示存在变化。文件结构需要固定
        @in     -src_path       -标注文件存放的路径
        @ret    -change_cnt     -[变化的像素数量, 总的像素数量]
    '''
    change_cnt = np.zeros(2, dtype=np.uint32)

    for dirpath, sub_dirs, files in os.walk(src_path):   
        if 'pin.txt' in files:      # find the control points     
            for fdr_a, fdr_b in itertools.combinations(sub_dirs, 2):   #select two of all the folders
                for json_folder in os.listdir(os.path.join(dirpath, fdr_a)):
                    if os.path.isdir(os.path.join(dirpath, fdr_a, json_folder)):
                        number = json_folder[-9:-5]     # patch number，RS2 这里是 4 位数字，GF3这里是3位数字，需要注意

                        # the folder A
                        lbl_idx_a, _  = read_label_png(os.path.join(dirpath, fdr_a, json_folder))
                        lbl_idx_a = mask_label(lbl_idx_a, label_names_all, ('road', 'otherthings'))

                        # the folder B
                        # print(os.path.join(dirpath, fdr_b, fdr_b+number+'_json'))
                        if not osp.isdir(osp.join(dirpath, fdr_b, fdr_b+'_'+number+'_json')):
                            continue
                        lbl_idx_b, _  = read_label_png(os.path.join(dirpath, fdr_b, fdr_b+'_'+number+'_json'))
                        lbl_idx_b = mask_label(lbl_idx_b, label_names_all, ('road', 'otherthings'))

                        # compare and get the change detection results, ignore the _background_ class
                        # 0 indicates _background_, 1 indicates unchanged, 2 indicates changed
                        lbl_cd_idx = (lbl_idx_a != lbl_idx_b).astype(np.uint8) 
                        lbl_cd_idx += 1
                        lbl_cd_idx[(lbl_idx_a==0) | (lbl_idx_b==0)] = 0
                        print(os.path.join(dirpath, fdr_a+'-'+ fdr_b + '-' + number + '-change.png'))
                        # clrmap = np.array([[0,0,0],[255, 255, 255],[0,255,0]])
                        clrmap = np.array([[128, 128, 128], [0, 0, 0], [255, 255, 255]])
                        lblsave(os.path.join(dirpath, fdr_a+'--'+fdr_b + '-'+number+'-change.png'), lbl_cd_idx, clrmap)
                        change_cnt[0] += (lbl_cd_idx==2).sum()
                        change_cnt[1] += 512**2
                        # if not cv2.imwrite(os.path.join(dirpath, fdr_a+'-'+fdr_b + '-change.png'), lbl_cd_idx):
                        #     raise Error('change labels save failed')
    return change_cnt


def check_label_name(src_path, lbl_names_all):
    ''' check whether the category names in label_names.txt belongs to a specified name set 
        @in     -src_path       - root path, all of whose files should be checked
                -lbl_names_all  - specified name set
    '''
    for root, dirs, files in os.walk(src_path):
        for file in files:
            if '.json' in file:
                    with open(osp.join(root, file)) as f:
                        data = json.load(f)
                        for shape in data["shapes"]:
                            label_name = shape["label"]
                            if label_name not in label_names_all:
                                print(f'undefined {label_name} in {osp.join(root, file)}')

    print('check done')

def generate_and_get_label_statistics(src_path:str, label_names_all:Union[list, tuple]):
    ''' [deprecated] 获取由 labelme 产生的语义分割标注文件的统计信息、生成变化检测的label，然后统计变化的像素，变化检测的label中 0 表示 _background_, 1 表示无变化, 2 表示存在变化
        @in     -src_path       -标注文件存放的路径
        @ret    -cls_cnt        -不同类别对应的像素数量
                -change_cnt     -变化的像素数量
    '''
    cls_cnt = np.zeros(len(label_names_all), dtype=np.uint32)
    change_cnt = np.zeros(2, dtype=np.uint32)

    for dirpath, sub_dirs, files in os.walk(src_path):

        # statistics of semantic labels
        if 'label.png' in files:
            lbl_idx, lbl_name = read_label_png(os.path.join(dirpath, 'label.png'))
            lbl_idx = reconstrcut_label(lbl_idx, lbl_name, label_names_all)
            hist, _ = np.histogram(lbl_idx, range(len(label_names_all)+1))
            cls_cnt += hist.astype(np.uint32)
        
        # statistics of changed pixels
        elif 'pin.txt' in files:      # find the control points
            for fdr_a, fdr_b in itertools.combinations(sub_dirs, 2):   #select two of all the folders
                # mylib.mkdir_if_not_exist(os.path.join(dirpath, fdr_a+'-'+fdr_b))
                for json_folder in os.listdir(os.path.join(dirpath, fdr_a)):
                    if os.path.isdir(os.path.join(dirpath, fdr_b, json_folder)):
                        
                        number = json_folder[-9:-5]     # patch number

                        # json_parent_dir = os.path.join(dirpath, fdr_a)
                        # change_cnt[0] = read_and_compare(json_parent_dir, json_folder, fdr_b+'_'+number+'_json', label_names_all, number)
                        # change_cnt[1] += 2*512**2

                        # the folder A
                        (lbl_idx_a, lbl_name_a)  = read_label_png(os.path.join(dirpath, fdr_a, json_folder))
                        lbl_idx_a = reconstrcut_label(lbl_idx_a, lbl_name_a, label_names_all)
                        lbl_idx_a = mask_label(lbl_idx_a, label_names_all, ('road', 'otherthings'))

                        # the folder B
                        # print(os.path.join(dirpath, fdr_b, fdr_b+number+'_json'))
                        # 文件结构需要固定
                        (lbl_idx_b, lbl_name_b)  = read_label_png(os.path.join(dirpath, fdr_b, fdr_b+'_'+number+'_json'))
                        lbl_idx_b = reconstrcut_label(lbl_idx_b, lbl_name_b, label_names_all)
                        lbl_idx_b = mask_label(lbl_idx_b, label_names_all, ('road', 'otherthings'))

                        # compare and get the change detection results, ignore the _background_ class
                        # 0 indicates _background_, 1 indicates unchanged, 2 indicates changed
                        lbl_cd_idx = (lbl_idx_a != lbl_idx_b).astype(np.uint8) 
                        change_cnt[0] += lbl_cd_idx.sum()
                        change_cnt[1] += 2*512**2
                        lbl_cd_idx += 1
                        # print((lbl_cd_idx==1).sum())
                        # unu = (lbl_idx_a==0) | (lbl_idx_b==0)
                        # print((unu==True).sum())
                        lbl_cd_idx[(lbl_idx_a==0) | (lbl_idx_b==0)] = 0
                        print(os.path.join(dirpath, fdr_a+'-'+ fdr_b + '-' + number + '-change.png'))
                        # clrmap = np.array([[0,0,0],[255, 255, 255],[0,255,0]])
                        clrmap = np.array([[128, 128, 128], [0, 0, 0], [255, 255, 255]])
                        lblsave(os.path.join(dirpath, fdr_a+'--'+fdr_b + '-'+number+'-change.png'), lbl_cd_idx, clrmap)
                        # if not cv2.imwrite(os.path.join(dirpath, fdr_a+'-'+fdr_b + '-change.png'), lbl_cd_idx):
                        #     raise Error('change labels save failed')

        # 第二种格式的数据存储，来自赵嘉麟
        elif 'pin-2.txt' in files:
            for number in sub_dirs:
                if os.path.isdir(os.path.join(dirpath, number)):
                    paulis =  os.listdir(os.path.join(dirpath, number))
                    paulis = filter(lambda x:os.path.splitext(x)[1] == '', paulis)
                    for fdr_a, fdr_b in itertools.combinations(paulis, 2):   #select two of all the folders
                        # the folde A
                        (lbl_idx_a, lbl_name_a)  = read_label_png(os.path.join(dirpath, number, fdr_a))
                        lbl_idx_a = reconstrcut_label(lbl_idx_a, lbl_name_a, label_names_all)
                        lbl_idx_a = mask_label(lbl_idx_a, label_names_all, ('road', 'otherthings'))

                        # the folder B
                        (lbl_idx_b, lbl_name_b)  = read_label_png(os.path.join(dirpath, number, fdr_b))
                        lbl_idx_b = reconstrcut_label(lbl_idx_b, lbl_name_b, label_names_all)
                        lbl_idx_b = mask_label(lbl_idx_b, label_names_all, ('road', 'otherthings'))

                        # compare and get the change detection results, ignore the _background_ class
                        # 0 indicates _background_, 1 indicates unchanged, 2 indicates changed
                        lbl_cd_idx = (lbl_idx_a != lbl_idx_b).astype(np.uint8) 
                        change_cnt[0] += lbl_cd_idx.sum()
                        change_cnt[1] += 2*512**2
                        lbl_cd_idx += 1
                        lbl_cd_idx[(lbl_idx_a==0) | (lbl_idx_b==0)] = 0
                        print(os.path.join(dirpath, fdr_a+'-'+fdr_b + '-change.png'))
                        clrmap = np.array([[128, 128, 128], [0, 0, 0], [255, 255, 255]])
                        # clrmap = np.array([[0,0,0],[255, 255, 255],[0,255,0]])
                        lblsave(os.path.join(dirpath, fdr_a+'--'+fdr_b + '-'+number+'-change.png'), lbl_cd_idx, clrmap)

    # write to excel file
    df = pd.DataFrame(data=np.concatenate((cls_cnt, change_cnt), axis=0).reshape(1, -1), columns=list(label_names_all)+['changed', 'all'])
    df.to_excel(os.path.join(src_path, 'statitics_20_11_27.xlsx'), index=False)
    return (cls_cnt, change_cnt)


if __name__=='__main__':
    ''' -------------这段最好不要改------------------ '''
    label_names_all = ('_background_', 'water', 'farmland', 'unusedland', 'building', 'otherthings', 'mountainland', 'woodland', 'road')
    ''' ^^^^^^^^^^^^^这段最好不要改^^^^^^^^^^^^^^^^^^ '''

    # src_path = r'E:\BaiduNetdiskDownload\RADATSAT-2'
    src_path = r'/data/csl/SAR_CD/RS2'
    

    # '''' >>>>>>>>>>   test generate_change_label() >>>>>>> '''
    # check_label_name(src_path, label_names_all)
    # json_to_dataset_batch(src_path, label_names_all)
    # change_cnt = generate_change_label(src_path, label_names_all)
    # print('change count:', change_cnt)
    cls_cnt, change_cnt  = get_label_statistics(src_path, label_names_all)
    print('class count:', cls_cnt, '\nchange detection count:', change_cnt)
    # '''' ^^^^^^^^^^^^^^^^   test generate_change_label() ^^ '''

    # '''' >>>>>>>>>>   test generate_and_get_label_statistics() >>>>>>> '''
    # json_to_dataset_batch(src_path, label_names_all)
    # cls_cnt, change_cnt = generate_and_get_label_statistics(src_path, label_names_all)
    # print('class count:', cls_cnt, '\nchange count:', change_cnt)
    # '''' ^^^^^^^^^^^^^^^^   test generate_and_get_label_statistics() ^^ '''


    # write to excel file
    # df = pd.DataFrame(data=np.concatenate((cls_cnt, change_cnt), axis=0).reshape(1, -1), columns=list(label_names_all)+['changed', 'all'])
    # df.to_excel(os.path.join(src_path, 'statitics_20_11_27.xlsx'), index=False)



    '''' >>>>>>>>>>>>>>>>>>   test mask_label() >>>>>>>>>>>>>>>>>> '''
    # change_name = ('road', 'otherthings')
    # tmp = np.ones((5,1), dtype=np.uint8)
    # a = np.concatenate((tmp, tmp*2, tmp*3, tmp*2, tmp*5, tmp*0, tmp*4, tmp*6, tmp*7), axis=1)
    # b = mask_label(a, label_names_all, change_name)
    # print('a=\n', a, '\n\nb=\n', b)
    '''' ^^^^^^^^^^^^^^^^^^^^^^   test mask_label() ^^^^^^^^^^^^ '''


    ''' >>>>>>>>>>>>>>>>>>  test reconstruct_label(), success >>>>>>>>>>>>>>>>>>'''
    # lbl_name = ('farmland', '_background_', 'building', 'unusedland', 'water', 'woodland')
    # tmp = np.ones((2,5), dtype=np.uint8)
    # lbl_idx = np.concatenate((tmp*0, tmp, tmp*2, tmp*3, tmp*4, tmp*5), axis=0)
    # print(lbl_idx.shape, '\n', lbl_idx, '\n\n')
    # lbl_idx_new = reconstrcut_label(lbl_idx, lbl_name, label_names_all)
    # print(lbl_idx_new, lbl_idx_new.dtype)
    '''  ^^^^^^^^^^^^^^^ test reconstruct_label() ^^^^^^^^^^^^^^^^^^^^^^^^ '''

    ''' >>>>>>>>>>>>>>>>>>  test json_to_dataset_batch(), success >>>>>>>>>>>>>>>>>>'''
    # src_path = r'F:\BaiduYunDownload\54所极化SAR变化检测项目-数据标注\GaoFeng-3\日本鞍手郡-E130N34'
    # json_to_dataset_batch(src_path)
    '''  ^^^^^^^^^^^^^^^ test json_to_dataset_batch() ^^^^^^^^^^^^^^^^^^^^^^^^ '''

    ''' >>>>>>>>>>>>>>>>>>  test get_corrds_from_slice_idx(), success '''
    # for ii in range(9):
    #     print(ii, '--', get_corrds_from_slice_idx([1024, 1024], [511,511], ii))
    '''  ^^^^^^^^^^^^^^^ test get_corrds_from_slice_idx() ^^^^^^^^^^^ '''