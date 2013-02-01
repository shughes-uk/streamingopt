import time
import subprocess
import psutil
import os
import re
import matplotlib.pyplot as plt
from PyQt4.QtGui import *
from PyQt4.QtCore import *
import sys 
from datetime import datetime
import threading
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
class CPUMon(threading.Thread):
	def __init__(self,pollInterval):
		threading.Thread.__init__(self)
		self.exiting = False
		self.pollInterval = pollInterval
		self.cpuPolls = []

	def run(self):
		self.start_time = time.time()
		while not self.exiting:
			self.cpuPolls.append(psutil.cpu_percent())
			time.sleep(self.pollInterval)
		self.end_time = time.time()

	def stop(self):
		self.exiting = True
		self.join()

	def getAvg(self):
		if self.exiting:
			total_cpu_polls = sum(self.cpuPolls)
			num_polls = len(self.cpuPolls)
			return total_cpu_polls/num_polls
		else:
			return 0
	def getMax(self):
		if self.exiting:
			return max(self.cpuPolls)
		else:
			return 0

class X264Thread(QThread):

	jobFinishedSignal = pyqtSignal(object)

	def __init__(self,preset,fps,crf,vbv_maxrate,vbv_bufsize,input_file,resolution,frames,parent):
		QThread.__init__(self)
		self.exiting = False
		self.preset = preset
		self.fps = fps
		self.crf = crf
		self.vbv_maxrate = vbv_maxrate
		self.vbv_bufsize = vbv_bufsize
		self.input_file = input_file
		self.resolution = resolution
		#TODO if linux/osx output to dev/null
		self.output = 'NUL'
		self.frames = frames

	def cancel(self):
		if self.p.returncode is None:
			self.p.terminate()
		self.wait()

	def readLog(self,p):
		try:
			currentline = ''
			log = []
			while p.poll() == None:
				currentline += p.stdout.read(10)
				currentline = currentline.replace('\r','\n')
				newlines = currentline.split('\n')
				if len(newlines) > 1:
					if len(newlines[0].replace(' ','')) > 0:
						print repr(newlines[0])
						log.append(newlines[0])
					currentline  = ''.join(newlines[1:])
			#execution is finished , grab the last of the data from the buffer
			currentline += p.stdout.read().replace('\r','\n')
			newlines = currentline.split('\n')
			for x in newlines:
				if len(x.replace(' ','')) > 0:
					print repr(x)
					log.append(x)
			return log
		except Exception, e:
			print e

	def run(self):
		try:
			print 'Rendering test clip with settings :'
			print '\t Preset : ' + self.preset
			print '\t FPS : %i' %self.fps
			print '\t CRF : %i' %self.crf
			print '\t VBV MaxRate : %i' %self.vbv_maxrate
			print '\t VBV Buffer : %i' %self.vbv_bufsize
			print '\t Resolution :'
			print '\t\t Height : %i' %self.resolution[1]
			print '\t\t Width : %i' %self.resolution[0]
			
			#note x264 logs to stderr instead of stdout
			#because it is shit
        
			cpuMonitor = CPUMon(0.1)
			self.p = subprocess.Popen(	['x264.exe' ,  
								'--preset' , str(self.preset) ,
								'-o', self.output , 
								'--fps', str(self.fps) ,
								'--frames', str(self.frames),
								'--crf' , str(self.crf) ,
								'--vbv-maxrate' , str(self.vbv_maxrate) ,
								'--vbv-bufsize' , str(self.vbv_bufsize) ,
								'--ssim',
								'--video-filter' , "resize:%i,%i" %(self.resolution[0],self.resolution[1]) ,
								'test.mp4'
								],
								stderr=subprocess.STDOUT,
								stdout=subprocess.PIPE,
								shell=False
							)
			cpuMonitor.start()
			log = self.readLog(self.p)
			cpuMonitor.stop()
			#cpuMonitor.join()
			FPS_string = log[-1]
			SSIM_string = log[-3]
			r_result = re.search(FPS_RGEX,FPS_string)
			avg_fps = float(r_result.group(1))
			r_result = re.search(SSIM_RGEX,SSIM_string)
			ssim = float(r_result.group(1))
			print 'Results :'
			print '\t Average CPU : %f' %cpuMonitor.getAvg()
			print '\t Max CPU : %f' %cpuMonitor.getMax()
			print '\t Average FPS : %f' %avg_fps
			print '\t SSIM : %f' %ssim
			self.jobFinishedSignal.emit({ 'avg_cpu':cpuMonitor.getAvg() ,'max_cpu':cpuMonitor.getMax() , 'avg_fps':avg_fps , 'ssim':ssim })
		except Exception , e:
			print e

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
				result['testresults'] = DoTest(vbv_bufsize=VBR_MAX*2,vbv_maxrate=VBR_MAX,crf=test_crf,resolution=resolution,preset=preset)
				if result['testresults']['avg_fps'] < 30:
					break
				results_presets.append( result )
			if len(results_presets) > 0:
				results_resolution.append(results_presets)
		if len(results_resolution) > 0:
			results.append(results_resolution)
			

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
			plt.plot(to_plot_x,to_plot_y)
			#plt.show()

	plt.ylabel('ssim')
	plt.xlabel('avg_cpu')
	plt.show()

	

		
	#average_cpu , max_cpu , avg_fps , ssim = DoTest()

#Optimize()

class QtTextLogger(QObject):

	messageSignal = pyqtSignal(object)

	def __init__(self,out=None,color=None):
		QObject.__init__(self)
		self.out = out
		self.color = color
		
	def write(self,message):
		if message == '\n':
			return
		t = datetime.now()
		self.messageSignal.emit(('%i:%i:%i : ' %(t.hour,t.minute,t.second) + message,self.color))
		if self.out:
			self.out.write('%i:%i:%i : ' %(t.hour,t.minute,t.second) + message + '\n')

class QResolutionItem(QStandardItem):
	def __init__(self,resolution):
		super(QStandardItem,self).__init__()
		self.resolution = resolution
		self.setText(resolution)
		self.result = None

	def update(self):
		for presetItemIndex in range(0,self.rowCount()):
			presetItem = self.child(presetItemIndex)
			presetItem.update()
			if presetItem.tested:
				if presetItem.result == 'yes':
					self.setBackground(QColor(0,255,0))
					self.result = 'yes'
				elif presetItem.result == 'maybe' and self.result != 'yes':
					self.setBackground(QColor(255,140,0))
					self.result = 'maybe'
				elif presetItem.result == 'no' and self.result != 'yes' and self.result != 'maybe':
					self.setBackground(QColor(255,0,0))
					self.result = 'no'



class QPresetItem(QStandardItem):
	def __init__(self,preset):
		super(QStandardItem,self).__init__()
		self.tested = False
		self.result = None
		self.preset = preset
		self.setText(preset)

	def update(self):
		for crfItemIndex in range(0,self.rowCount()):
			crfItem = self.child(crfItemIndex)
			crfItem.update()
			if crfItem.tested:
				self.tested = True
				if crfItem.result == 'yes':
					self.setBackground(QColor(0,255,0))
					self.result = 'yes'
				elif crfItem.result == 'maybe' and self.result != 'yes':
					self.setBackground(QColor(255,140,0))
					self.result = 'maybe'
				elif crfItem.result == 'no' and self.result != 'yes' and self.result != 'maybe':
					self.setBackground(QColor(255,0,0))
					self.result = 'no'


class QCRFItem(QStandardItem):
	def __init__(self,CRF):
		super(QStandardItem,self).__init__()
		self.tested = True
		self.result = 'maybe'
		self.CRF = CRF
		self.setText(CRF)

	def update(self):
		if self.result is 'maybe':
			#orange
			self.setBackground(QColor(255,140,0))
		elif self.result is 'no':
			#red
			self.setBackground(QColor(255,0,0))
		elif self.result is 'yes':
			#green
			self.setBackground(QColor(0,255,0))

class MainWindow(QWidget):
	def __init__(self):
		super(MainWindow,self).__init__()
		self.initUI()

	def initUI(self):
		self.setGeometry(50,50,800,640)
		self.setWindowTitle('X264 Streaming Optimizer')
		
		self.SetUpLog()

		self.GoButton = QPushButton('Go',self)
		self.GoButton.resize(self.GoButton.sizeHint())
		self.GoButton.move(600,600)
		self.connect(self.GoButton, SIGNAL("clicked()"), self.StartJerb)

		self.CancelButton = QPushButton('Cancel',self)
		self.CancelButton.resize(self.CancelButton.sizeHint())
		self.CancelButton.move(500,500)
		self.connect(self.CancelButton,SIGNAL("clicked()"), self.StopJerb)

		self.TestsTree = QTreeView(self)
		self.BuildTestsModel()
		self.TestsTree.setModel(self.model)
		self.TestsTree.resize(200,500)
		self.TestsTree.move(25,25)	

		self.show()
		#Optimize()

	def SetUpLog(self):
		self.OutTextEdit = QTextBrowser(self)
		sys.stdout = QtTextLogger(sys.stdout)
		sys.stderr = QtTextLogger(sys.stderr,QColor(255,0,0))
		sys.stdout.messageSignal.connect(self.LogToWindow)
		sys.stderr.messageSignal.connect(self.LogToWindow)
		self.OutTextEdit.resize(525,200)
		self.OutTextEdit.move(250,25)
		print 'Console Logging initialized'
		print >> sys.stderr, 'spam'
	
	def LogToWindow(self,msgclr):
		if msgclr[1]:
			tc = self.OutTextEdit.textColor()
			self.OutTextEdit.setTextColor(msgclr[1])
			self.OutTextEdit.append(msgclr[0])
			self.OutTextEdit.setTextColor(tc)
		else:
			self.OutTextEdit.append(msgclr[0])

	def StartJerb(self):
		self.wThread = X264Thread(preset='ultrafast',fps=30,crf=35,vbv_maxrate=1500,vbv_bufsize=3000,input_file='test.mp4',resolution=RESOLUTIONS['480p'],frames=100,parent=self)
		self.wThread.jobFinishedSignal.connect(self.X264Finish)
		self.wThread.start()

	def StopJerb(self):
		self.wThread.cancel()

	def X264Finish(self,result):
		print result


	def BuildTestsModel(self):
		self.model = QStandardItemModel()
		for resolution in RESOLUTIONS:
			resolution_item = QResolutionItem(resolution)
			resolution_item.setEditable(False)
			for preset in PRESETS:
				preset_item = QPresetItem(preset)			
				preset_item.setEditable(False)
				for crf in range(CRF_MIN,CRF_MAX+1):
					crf_item = QCRFItem(str(crf))
					crf_item.setEditable(False)
					preset_item.appendRow(crf_item)					
				resolution_item.appendRow(preset_item)
			resolution_item.update()
			self.model.appendRow(resolution_item)
	


app = QApplication(sys.argv)

w = MainWindow()

sys.exit(app.exec_())
