import time
import subprocess
import psutil
import os
import re
import matplotlib.pyplot as plt
#xsplit uses between 25-35 CRF
CRF_MAX = 35
CRF_MIN = 30
VBR_MAX = 400
VBUFF = VBR_MAX * 2
MAX_CPU = 85
PRESETS = ['ultrafast','superfast','veryfast','faster','fast','medium','slow','slower','veryslow','placebo']
RESOLUTIONS = {'720p':(1280,720),'1080p':(1920,1080),'480p':(854,480)}
FPS_ = [30,60]
SSIM_RGEX = r'SSIM Mean Y:(\d.\d+)'
FPS_RGEX = r'(\d+.\d+) fps'
MLP_COLORS = ['b','g','r','c','m','y','k','w']
MLP_LINES = ['-','--','-.',':','.',',','o','v','^','<']
print 'Input your max vbr :'
#VBR_MAX = input()
print 'Choose your input resolution :'
print '1) 1080p'
print '2) 720p'
print '3) 480p'
print 'Choose your input fps :'
print '1) 30fps'
print '2) 60fps'

"""	480p
		30 fps
			ultrafast --> placebo
				CRF 35 --> CRF 21

		60 fps
			ultrafast --> placebo
				CRF 35 --> CRF 21

	720p
		30 fps 
			ultrafast --> placebo
				CRF 35 --> CRF 21

		60 fps 
			ultrafast --> placebo
				CRF 35 --> CRF 21

	1080p
		30 fps
			ultrafast --> placebo
				CRF 35 --> CRF 21
		60 fps 
			ultrafast --> placebo
				CRF 35 --> CRF 21

"""



def DoTest(preset='superfast',fps=30,crf=25,vbv_maxrate=3000,vbv_bufsize=6000,input='test.mp4' , resolution=(854,480) ):
	print 'Rendering test clip with settings :'
	print '\t Preset : ' + preset
	print '\t FPS : %i' %fps
	print '\t CRF : %i' %crf
	print '\t VBV MaxRate : %i' %vbv_maxrate
	print '\t VBV Buffer : %i' %vbv_bufsize
	print '\t Resolution :'
	print '\t\t Height : %i' %resolution[1]
	print '\t\t Width : %i' %resolution[0]
	p = subprocess.Popen(	['x264.exe' ,  
						'--preset' , str(preset) ,
						'-o', 'NUL' , 
						'--fps', str(fps) ,
						'--frames', '1000' ,
						'--crf' , str(crf) ,
						'--vbv-maxrate' , str(vbv_maxrate) ,
						'--vbv-bufsize' , str(vbv_bufsize) ,
						'--ssim',
						'--video-filter' , "resize:%i,%i" %(resolution[0],resolution[1]) ,
						'test.mp4'
						],
						stderr=open('log','w')
					)
	start_time = time.time()
	things = []
	while p.poll() == None:
		things.append(psutil.cpu_percent())
		time.sleep(0.1)
	end_time = time.time()
	total_time = end_time - start_time
	total_cpu_polls = sum(things)
	num_polls = len(things)
	avg_cpu = total_cpu_polls/num_polls
	max_cpu = max(things)
	logfile = open('log','r').readlines()
	FPS_string = logfile[-1]
	SSIM_string = logfile[-4]
	r_result = re.search(FPS_RGEX,FPS_string)
	avg_fps = float(r_result.group(1))
	r_result = re.search(SSIM_RGEX,SSIM_string)
	ssim = float(r_result.group(1))
	print 'Results :'
	print '\t Average CPU : %f' %avg_cpu
	print '\t Max CPU : %f' %max_cpu
	print '\t Average FPS : %f' %avg_fps
	print '\t SSIM : %f' %ssim
	return { 'avg_cpu':avg_cpu ,'max_cpu':max_cpu , 'avg_fps':avg_fps , 'ssim':ssim }

def Optimize():
	#preset = PRESETS[0]
	resolution = RESOLUTIONS['480p']
	#max out CRF for each preset
	results = []
	results_resolution = []
	results_presets = []
	for resolution in RESOLUTIONS.values():
		results_resolution = []
		for preset in PRESETS:
			results_presets = []
			for test_crf in reversed(range(CRF_MIN , CRF_MAX + 1)):
				result = { 'preset' : preset , 'resolution' : resolution , 'crf' : test_crf }
				print VBR_MAX
				result['testresults'] = DoTest(vbv_bufsize=VBR_MAX*2,vbv_maxrate=VBR_MAX,crf=test_crf,resolution=resolution,preset=preset)
				if result['testresults']['avg_fps'] < 30:
					break
				results_presets.append( result )
			if len(results_presets) > 0:
				results_resolution.append(results_presets)
		if len(results_resolution) > 0:
			results.append(results_resolution)
		break	

	colors = list(MLP_COLORS)
	lines = list(MLP_LINES)
	#print results
	for resolution_results in results:
		for preset_results in resolution_results:
			to_plot_x = []
			to_plot_y = []
			for crf_result in preset_results:				
				to_plot_x.append(crf_result['testresults']['avg_cpu'])
				to_plot_y.append(crf_result['testresults']['ssim'])
			print to_plot_x
			print to_plot_y
			plt.plot(to_plot_x,to_plot_y)
			#plt.show()

	plt.ylabel('ssim')
	plt.xlabel('avg_cpu')
	plt.show()

	

		
	#average_cpu , max_cpu , avg_fps , ssim = DoTest()

Optimize()