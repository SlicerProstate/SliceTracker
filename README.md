![Alt text](SliceTracker/Resources/Icons/SliceTracker.png)


### Intro

SliceTracker is a 3D Slicer (see http://slicer.org) extension designed to support in-bore MRI-guided targeted prostate biopsy, as further elaborated in the following sections:

* planning of the procedure
* calibration of the intra-procedural image frame of reference with the biopsy template
* re-identification of the pre-procedurally defined targets in the intra-procedural images
* automated segmentation of the prostate gland to facilitate image registration
* automated, continuous tracking of the identified targets during the course of the procedure by means of deformable intensity-based registration
* consistent collection of the relevant data during the course of the procedure (images, results of segmentation and registration, target tracking)
* visualization of the intra-procedural images and support of specialized hanging protocols to facilitate needle tracking, biopsy template and calibration device visualization, assessment of the image registration results, etc.
* ...

Video demonstration of the extension capabilities will be linked from here shortly.

This module is a work in progress and is not currently released as a 3D Slicer extension, and thus is not available in the 3D Slicer ExtensionManager.

### Functionality

The content below is outdated and will be updated at the time of the official release of the extension ...

The module guides the user through a workflow that consists of the following steps:

**1. Select incoming DICOM-series**
  
  The user is supposed to start with choosing the patient ID. The modules expects that the patient is already loaded into       local slicer dicom database. Relevant patient information (ID, Name, Date of Birth, Date of Study) are shown above the        module for easy inspection. Once the patient is selected, the preprocedural directory should be chosen, containing the        diagnstoic pre-procedural scan, the label of the prostate gland and the targets (see section [*Data                           conventions*](https://github.com/PeterBehringer/Registration/blob/master/README.md#data-conventions) to learn about what      type of strucutre and formats are expected). The last step is selecting the intra-procedural directory where new DICOM        series are supposed to be detected and presented to the user if they are relevant to the procedure. The user can select the   series that is incoming and importing it to slicer using the *load and segment*-button. In case of arriving patient data      that does not correlate to the choosed patient, the software will warn the user. 

**2. Create intra-procedural label**

  For minimizing the computation time that is required by deformable registration, the user can specify regions of interest of   the structure to be registred. Therefore, two different modes (quick mode, label mode) are provided. Once the label is        created, the user is supposed to proceed by clicking the registration tab. 
  
**3. Perform B-Spline registration**

  By following previous steps of the workflow, the user only needs to check visually if the input parameters are set            correctly. Registration parameters have been optimized in previous studies [1] and are not configuratable by the end-user.    Registration is performed using rigid, affine and deformable B-Spline stages applied in sequence.                             [BRAINSFit](https://github.com/BRAINSia/BRAINSTools/tree/master/BRAINSFit) with ITKv4 is used as underlaying library. 
  
**4. Visual evaluation of registration result**

  Showing the result of all three registration stages enables quick troubleshooting in a very comprehensible way. The user can   switch between the results and compare the registered pre-procedural image with the intra-procedural. There are four          different tools and different visualization modes provided to compare the resulting image volume and target. Furthermore, a   needle tip can be set to measure the distance between each registered target and the needle tip. 

### Prerequisites, conventions and testing

If you want to test the module, please follow these steps:

1. make sure to install [VolumeClip](https://www.slicer.org/slicerWiki/index.php/Documentation/Nightly/Extensions/VolumeClip) from the slicer extension manager. (view -> Extension Manager)
2. make sure to install [mpReview](https://github.com/SlicerProstate/mpReview) from the slicer extension manager. (view -> Extension Manager)
3. you will need to preprocess your pre-op data with [mpReview](https://github.com/SlicerProstate/mpReview)
4. after preprocessing is done, run SliceTracker and select the output directory for your mpReview preprocessed data
5. select intra-op data directory (where incoming DICOM data will be or already has been received)
6. click "Track targets"
7. segment the whole gland and start registration
8. result can be viewed and retried, skipped or approved

### Contact

Please feel free to contact us for questions, feedback, suggestions, bugs, or you can create issues in the issue tracker: https://github.com/SlicerProstate/SliceTracker/issues

* [Andrey Fedorov](https://github.com/fedorov) fedorov@bwh.harvard.edu

* Christian Herz cherz@bwh.harvard.edu

* Peter Behringer peterbehringer@gmx.de

### Acknowledgments

This work is supported in part by NIH grants 

* P41 EB015898 National Center for Image Guided Therapy (NCIGT), http://ncigt.org
* U24 CA180918 Quantitative Image Informatics for Cancer Research (QIICR), http://qiicr.org


### Literature

1. Fedorov A, Tuncali K, Fennessy FM, et al. Image Registration for Targeted MRI-guided Transperineal Prostate Biopsy. Journal of magnetic resonance imaging : JMRI. 2012;36(4):987-992. doi:10.1002/jmri.23688.
2. Behringer PA, Herz C, Penzkofer T, Tuncali K, Tempany CM, Fedorov A. Open-­source Platform for Prostate Motion Tracking during in­-bore Targeted MRI­-guided Biopsy. Int Conf Med Image Comput Comput Assist Interv. 2015 Oct;18(WS). Workshop on Clinical Image-based Procedures: Translational Research in Medical Imaging.
3. http://slicerprostate.github.io/ProstateMotionStudy/
