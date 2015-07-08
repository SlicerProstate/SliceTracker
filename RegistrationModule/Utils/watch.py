__author__ = 'Christian'

import sys, getopt, os
import time

class NotDirectoryError(Exception):
  pass

class DICOMDirectoryObserver(object):

  def __init__(self, directory, host, port):
    if not os.path.isdir(directory):
      raise NotDirectoryError("The directory is actually no directory")
    self.directory = directory
    self.host = host
    self.port = port
    self.numberOfFiles = len(os.listdir(self.directory))

  def watch(self, secondsToWait=1):
    while True:
      numberOfFiles = len([item for item in os.listdir(self.directory)])

      if self.numberOfFiles < numberOfFiles:
        print "Number of files changed"
        self.startStoreSCU()

      self.numberOfFiles = numberOfFiles
      time.sleep(secondsToWait)

  def startStoreSCU(self):
    cmd=('sudo storescu ' + self.host + ' ' + self.port + ' ' + self.directory + ' --scan-directories')
    print cmd
    os.system(cmd)

def main(argv):
   watchDirectory = ''
   host = ''
   port = ''
   interval = 1
   try:
      opts, args = getopt.getopt(argv,"i:d:h:p:?",["help","directory=","host=","port=","interval="])
   except getopt.GetoptError:
      print 'watch.py -d <watchDirectory> -h <host> -p <port> -i <interval [in seconds]>'
      sys.exit(2)
   for opt, arg in opts:
      if opt in ("-?", "--help"):
         print 'watch.py -d <watchDirectory> -h <host> -p <port>'
         sys.exit()
      elif opt in ("-d", "--directory"):
         watchDirectory = arg
      elif opt in ("-h", "--host"):
         host = arg
      elif opt in ("-p", "--port"):
         port = arg
      elif opt in ("-i", "--interval"):
         interval = int(arg)
   if watchDirectory and host and port:
     print 'Directory to watch is: ', watchDirectory
     print 'Host to send DICOM files to is: ', host
     print 'Port to send DICOM files to is: ', port

     watcher = DICOMDirectoryObserver(directory=watchDirectory, host=host, port=port)
     watcher.watch(interval)

if __name__ == "__main__":
   main(sys.argv[1:])


#client use:  $ sudo storescp -v -p 104
#python watch.py -d "/Users/Christian/Documents/TEST1" -h localhost -p 104 -i 1