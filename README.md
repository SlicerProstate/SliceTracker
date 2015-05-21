# Registration


### Intro

EasyReg is a 3D Slicer (see http://slicer.org) module that facilitates registration of pre- and intraprocedural targetet prostate biopsy


### Functionality

The module guides the user through a workflow that consists of the following steps:


### Data organization conventions

For testing purposes, the module expects the following folder structure:

ATTENTION: every file in intraopDir is deleted with every reload! 

```
└── Resources
  └── Testing
      ├─── intraopDir
      ├─── preopDir
      │    ├── t2-label.nrrd
      │    ├── t2-N4.nrrd
      │    └── Targets.fcsv
      ├─── testData_1
      │    ├── xxx.dcm
      │    ├── ....
      │    └── xxx.dcm
      ├─── testData_2
      │    ├── xxx.dcm
      │    ├── ....
      │    └── xxx.dcm
      └─── testData_3
           ├── xxx.dcm
           ├── ....
           └── xxx.dcm
```

Please feel free to contact Peter Behringer peterbehringer@gmx.de for further feedback, suggestions, bugs.. 
