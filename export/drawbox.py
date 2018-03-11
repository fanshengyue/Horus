# -*- coding:utf-8 -*-
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy import text
import json
from ctypes import *
sys.path.append("..")
import util


class IMAGE(Structure):
	_fields_ = [("w", c_int),
				("h", c_int),
				("c", c_int),
				("data", POINTER(c_float))]


with open('/home/nvidia/Horus/config.cnf') as f:
	cnf = json.load(f)
lib = CDLL(str(cnf['darknet_path'])+'libdarknet.so', RTLD_GLOBAL)

free_image = lib.free_image
load_image=lib.load_image
load_image.argtypes = [c_char_p, c_int, c_int]
load_image.restype = IMAGE
load_image_color = lib.load_image_color
draw_box_width=lib.draw_box_width
save_image = lib.save_image


def drawbox(im,img_id,x,y,w,h,paintwidth):
	draw_box_width(im,int(x-w/2.),int(y-h/2.),int(x+w/2.),int(y+h/2.),int(paintwidth),255,0,0)
	with open('/home/nvidia/Horus/config.cnf') as f:
		cnf = json.load(f)
	save_image(im,cnf['detect_path']+'/'+img_id)
	free_image(im)

def queryDataByImgId(img_id):

	with open('/home/nvidia/Horus/config.cnf') as f:
		cnf = json.load(f)
		db = create_engine(cnf['db'])

		result=db.execute(text('select * from tb_object where img_id = :img_id'), {'img_id':img_id})
		data = result.fetchall()

		if len(data)>0:
			img=cnf['arc_path']+'/'+str(img_id)+'.jpg'

			if os.path.exists(img):
				imgs=cnf['detect_path']+"/"+str(img_id)+".jpg"
				util.copy_file(img,imgs)

				for s in data:
					if len(s[1])>0:
						if os.path.exists(imgs):
							im = load_image(imgs, 0, 0)
							drawbox(im,img_id,round(float((s[3]))),round(float((s[4]))),round(float((s[5]))),round(float((s[6]))),3)
					
			


def main():
	with open('/home/nvidia/Horus/config.cnf') as f:
		cnf = json.load(f)
	if os.path.exists(cnf['arc_path']):
		dirs=os.listdir(cnf['arc_path'])
		for i in range(0,len(dirs)):
			img_id=dirs[i].split('.')[0]
			queryDataByImgId(img_id)
			print(str(i+1)+"/"+str(len(dirs)))








