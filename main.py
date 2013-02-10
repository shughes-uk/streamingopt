import time
import subprocess
import psutil
import re
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from PyQt4.QtGui import *
from PyQt4.QtCore import *
from matplotlib.font_manager import FontProperties

import sys 
from datetime import datetime
import threading
#xsplit uses between 25-35 CRF
CRF_MAX = 35
CRF_MIN = 30
VBR_MAX = 400
VBUFF = VBR_MAX * 2
INPUT_FILE = 'test.mp4'
RENDER_FRAMES = 100
MAX_CPU = 85
PRESETS = ['ultrafast','superfast','veryfast','faster','fast','medium','slow','slower','veryslow','placebo']
RESOLUTIONS = {'720p':(1280,720),'1080p':(1920,1080),'480p':(854,480)}
FPS = [30,60]
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
		self.timePolls = []

	def run(self):
		self.start_time = time.time()
		while not self.exiting:
			self.cpuPolls.append(psutil.cpu_percent())
			self.timePolls.append(time.time()  - self.start_time)
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
	def __init__(self,test):
		QThread.__init__(self)
		self.test = test
		self.exiting = False
		self.preset = test.preset
		self.fps = FPS[0]
		self.crf = test.crf
		self.vbv_maxrate = VBR_MAX
		self.vbv_bufsize = VBUFF
		self.input_file = INPUT_FILE
		self.resolution = RESOLUTIONS[test.resolution]
		#TODO if linux/osx output to dev/null
		self.output = 'NUL'
		self.frames = RENDER_FRAMES

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

			self.test.results = TestResult(avg_fps,cpuMonitor.getAvg(),cpuMonitor,ssim)
			self.jobFinishedSignal.emit(self.test)
		except Exception , e:
			print e.message
	

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

class TestResult():
	def __init__(self,avg_fps,avg_cpu,cpuMon,ssim):
		self.avg_fps = avg_fps
		self.avg_cpu = avg_cpu
		self.cpuMon = cpuMon
		self.ssim = ssim


class Test():
	def __init__(self,resolution,preset,crf):
		self.resolution = resolution
		self.preset = preset
		self.crf = crf
		self.results = None


	def __repr__(self):
		return 'X264 Test ' + self.resolution + ' ' + self.preset + ' ' + str(self.crf)

class QResolutionItem(QStandardItem):
	def __init__(self,resolution):
		super(QStandardItem,self).__init__()
		self.resolution = resolution
		self.setText(resolution)
		self.setEditable(False)
		self.result = None
		self.tested = False

	def getHash(self):
		return str(self.tested) + str(self.resolution)

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
		self.setEditable(False)
		self.setText(preset)

	def getHash(self):
		return str(self.tested) + self.preset

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
	def __init__(self,test):
		super(QStandardItem,self).__init__()
		self.test_this = True
		self.tested = False
		self.result = 'maybe'
		self.test = test
		self.CRF = test.crf
		self.setText(str(test.crf))
		self.setEditable(False)
		self.results = None
	def getHash(self):
		return str(tested) + str(test)

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

class IndividualTestResultFrame(QFrame):
	def __init__(self,parent):
		super(QFrame,self).__init__(parent)
		self.resize(725,275)

		self.FPSLabel = QLabel(self)
		self.FPSLabel.move(550,10)
		self.FPSLabel.resize(150,15)

		self.MaxCpuLabel = QLabel(self)
		self.MaxCpuLabel.move(550,30)
		self.MaxCpuLabel.resize(150,15)

		self.SSIMLabel = QLabel(self)
		self.SSIMLabel.move(550,50)
		self.SSIMLabel.resize(150,15)

		self.rGraph = ResultGraphSingle(self,([1,1],[1,1]))

		self.hide()

	def show(self,tests):
		self.rGraph.hide()
		if type(tests) is list:
			cpuResults = []
			for test in tests:
				label = str(test.resolution) + '_' + str(test.preset) + '_' + str(test.crf)
				cpuResults.append((test.results.cpuMon.timePolls,test.results.cpuMon.cpuPolls,label))
			self.rGraph = ResultGraphMany(self,cpuResults)
			self.FPSLabel.hide()
			self.MaxCpuLabel.hide()
			self.SSIMLabel.hide()
		else:
			self.rGraph = ResultGraphSingle(self,(tests.results.cpuMon.timePolls,tests.results.cpuMon.cpuPolls))
			self.FPSLabel.setText('Average FPS : %i' %tests.results.avg_fps)
			self.MaxCpuLabel.setText('Avg CPU : %i' %tests.results.avg_cpu)
			self.SSIMLabel.setText('SSIM : %f' %tests.results.ssim)
			self.FPSLabel.show()
			self.MaxCpuLabel.show()
			self.SSIMLabel.show()

		self.rGraph.resize(525,275)
		self.rGraph.show()
		self.setFrameShape(QFrame.StyledPanel)
		super(QFrame,self).show()

class ResultGraphMany(FigureCanvas):
	def __init__(self,parent,lines):
		self.fig = Figure()
		self.fig.subplots_adjust(left=0.10, right=0.7, top=0.96, bottom=0.12)
		self.axes = self.fig.add_subplot(111)
		for line in lines:
			self.axes.plot(line[0],line[1],label=line[2])
		fontP = FontProperties()
   		fontP.set_size('small')
		self.axes.legend(bbox_to_anchor=(1.5, 1.0),prop = fontP)
		self.axes.set_ylim(0,100)
		self.axes.set_ylabel('CPU (%)')
		self.axes.set_xlabel('Time (seconds)')
		FigureCanvas.__init__(self,self.fig)
		self.setParent(parent)

class ResultGraphSingle(FigureCanvas):
	def __init__(self,parent,line):
		self.fig = Figure()
		self.fig.subplots_adjust(left=0.10, right=0.96, top=0.96, bottom=0.12)
		self.axes = self.fig.add_subplot(111)
		self.axes.plot(line[0],line[1])
		self.axes.set_ylim(0,100)
		self.axes.set_ylabel('CPU (%)')
		self.axes.set_xlabel('Time (seconds)')
		FigureCanvas.__init__(self,self.fig)
		self.setParent(parent)



class MainWindow(QWidget):
	def __init__(self):
		super(MainWindow,self).__init__()
		self.initUI()

	def initUI(self):
		self.setGeometry(50,50,1000,640)
		self.setWindowTitle('X264 Streaming Optimizer')
		
		self.SetUpLog()

		self.GoButton = QPushButton('Go',self)
		self.GoButton.resize(self.GoButton.sizeHint())
		self.GoButton.move(600,600)
		#self.connect(self.GoButton, SIGNAL("clicked()"), self.StartJerb)

		self.CancelButton = QPushButton('Cancel',self)
		self.CancelButton.resize(self.CancelButton.sizeHint())
		self.CancelButton.move(500,500)
		self.connect(self.CancelButton,SIGNAL("clicked()"), self.StopJerb)
		self.CancelButton.hide()

		self.TestsTree = QTreeView(self)
		self.BuildTestsModel()
		self.TestsTree.setModel(self.model)
		self.TestsTree.resize(200,500)
		self.TestsTree.move(25,25)	
		self.TestsTree.setContextMenuPolicy(Qt.CustomContextMenu)
		self.TestsTree.customContextMenuRequested.connect(self.OpenTreeMenu)
		self.TestsTree.connect(self.TestsTree.selectionModel(), SIGNAL("selectionChanged(QItemSelection, QItemSelection)"), self.SelectionChanged) 
		self.UpdateTestTree()
		self.ResultFrame = IndividualTestResultFrame(self)
		self.ResultFrame.move(250,250)

		#self.ResultFrame.show(testCRF)

		self.test_in_progress = False
		self.test_queue = []
		self.show()
		#self.BeginTests(reversed(self.tests))
		#Optimize()

	def SelectionChanged(self,newSelection,oldSelection):
		if len(self.TestsTree.selectedIndexes()) > 0:
			selectedIndex = self.TestsTree.selectedIndexes()[0]
			selected = self.model.itemFromIndex(selectedIndex)
			if type(selected) is QCRFItem:
				if selected.test.results:
					self.ResultFrame.show(selected.test)
			elif type(selected) is QPresetItem:
				tests = []
				for qCrfItem in self.getChildren(selected):
					if qCrfItem.test.results:
						tests.append(qCrfItem.test)
				if len(tests) > 0:
					self.ResultFrame.show(tests)
			elif type(selected) is QResolutionItem:
				tests = []
				for qPresetItem in self.getChildren(selected):
					for qCrfItem in self.getChildren(qPresetItem):
						if qCrfItem.test.results:
							tests.append(qCrfItem.test)
				if len(tests) > 0:
					self.ResultFrame.show(tests)



	def OpenTreeMenu(self,position):
		if len(self.TestsTree.selectedIndexes()) == 1:
			index = self.TestsTree.selectedIndexes()[0]
			item = self.model.itemFromIndex(index)
			if type(item) != QStandardItem:
				if item.tested == False:
					menu = QMenu()
					menu.addAction('Test')
					action = menu.exec_(self.TestsTree.viewport().mapToGlobal(position))
					if action:
						testlist = []
						if type(item) is QResolutionItem:
							for presetItem in self.getChildren(item):
								for crfItem in self.getChildren(presetItem):
									testlist.append(crfItem.test)

						elif type(item) is QPresetItem:
							for crfItem in self.getChildren(item):
								testlist.append(crfItem.test)

						elif type(item) is QCRFItem:
							testlist = [item.test]

						self.BeginTests(testlist)

    
	def BeginTests(self,tests):
		if self.test_in_progress:
			print 'Test already in progress'
		else:
			print 'Tests queued up'
			self.test_queue.extend(tests)
			self.StartX264Job(self.test_queue.pop())
			self.test_in_progress = True

	def StartX264Job(self,test):
		print 'Kicking off x264 job with ' + str(test)
		self.wThread = X264Thread(test)
		self.wThread.jobFinishedSignal.connect(self.X264Finish)
		self.wThread.start()

	def X264Finish(self,test):
		print 'Test Complete , results : '
		print test.results.avg_fps
		self.UpdateTestTree()
		if len(self.test_queue) > 0:
			print 'More tests in the queue moving to next one'
			self.StartX264Job(self.test_queue.pop())
		else:
			self.test_in_progress = False


	def SetUpLog(self):
		self.OutTextEdit = QTextBrowser(self)
		sys.stdout = QtTextLogger(sys.stdout)
		sys.stderr = QtTextLogger(sys.stderr,QColor(255,0,0))
		sys.stdout.messageSignal.connect(self.LogToWindow)
		sys.stderr.messageSignal.connect(self.LogToWindow)
		self.OutTextEdit.resize(725,200)
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

	def StopJerb(self):
		self.wThread.cancel()



	def BuildTestsModel(self):
		self.tests = []
		for resolution in RESOLUTIONS:
			for preset in PRESETS:
				for crf in range(CRF_MIN,CRF_MAX+1):
					self.tests.append(Test(resolution,preset,crf))

		self.model = QStandardItemModel()
		self.testedGroup = QStandardItem('Tested')
		self.testedGroup.setEditable(False)
		self.untestedGroup = QStandardItem('Untested')
		self.untestedGroup.setEditable(False)
		self.model.appendRow(self.untestedGroup)
		self.model.appendRow(self.testedGroup)

	def getChildren(self,standardItem):
		children = []
		for index in range(0,standardItem.rowCount()):
			children.append(standardItem.child(index))
		return children

	def UpdateTestTree(self):
		#this whole method is horrible and i feel bad for allowing it to exist
		#persist expanded item dumb hashes
		expandedTestedItems = []
		for rItem in self.getChildren(self.testedGroup):
			if self.TestsTree.isExpanded(rItem.index()):
				expandedTestedItems.append(rItem.getHash())
			for pItem in self.getChildren(rItem):
				if self.TestsTree.isExpanded(pItem.index()):
					expandedTestedItems.append(pItem.getHash())
		expandedUntestedItems = []
		for rItem in self.getChildren(self.untestedGroup):
			if self.TestsTree.isExpanded(rItem.index()):
				expandedUntestedItems.append(rItem.getHash())
			for pItem in self.getChildren(rItem):
				if self.TestsTree.isExpanded(pItem.index()):
					expandedUntestedItems.append(pItem.getHash())
		#nuke whatever exists
		self.testedGroup.removeRows(0,self.testedGroup.rowCount())
		self.untestedGroup.removeRows(0,self.untestedGroup.rowCount())
		#now the repopulation can begin at last....war is awful
		for test in self.tests:
			if test.results:
				self.AddTestToTree(self.testedGroup,test)
			else:
				self.AddTestToTree(self.untestedGroup,test)

		for expandedHash in expandedTestedItems:
			for rItem in self.getChildren(self.testedGroup):
				if rItem.getHash() == expandedHash:
					self.TestsTree.setExpanded(rItem.index(),True)
					break
				else:
					for pItem in self.getChildren(rItem):
						if pItem.getHash() == expandedHash:
							self.TestsTree.setExpanded(pItem.index(),True)
							break
		for expandedHash in expandedUntestedItems:
			for rItem in self.getChildren(self.untestedGroup):
				if rItem.getHash() == expandedHash:
					self.TestsTree.setExpanded(rItem.index(),True)
					break
				else:
					for pItem in self.getChildren(rItem):
						if pItem.getHash() == expandedHash:
							self.TestsTree.setExpanded(pItem.index(),True)
							break

	
	def AddTestToTree(self,treeRow,test):
		for resolutionItem in self.getChildren(treeRow):
			if resolutionItem.resolution == test.resolution:
				for presetItem in self.getChildren(resolutionItem):
					if presetItem.preset == test.preset:
						#found existing preset group , just add it
						newCRF = QCRFItem(test)
						presetItem.appendRow(newCRF)
						if test.results:
							newCRF.tested = True
						return
				#no preset ground found for it, create new one
				newPreset = QPresetItem(test.preset)
				newCRF = QCRFItem(test)
				newPreset.appendRow(newCRF)
				resolutionItem.appendRow(newPreset)
				if test.results:
					newPreset.tested = True
					newCRF.tested = True
				return
		#no resolution group found, create resolution group and preset group!
		newResolution = QResolutionItem(test.resolution)
		newPreset = QPresetItem(test.preset)
		newCRF = QCRFItem(test)
		newPreset.appendRow(newCRF)
		newResolution.appendRow(newPreset)
		treeRow.appendRow(newResolution)
		if test.results:
			newResolution.tested = True
			newPreset.tested = True
			newCRF.tested = True
		return

	


app = QApplication(sys.argv)

w = MainWindow()

sys.exit(app.exec_())
