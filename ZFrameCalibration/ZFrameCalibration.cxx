#include "itkImage.h"
#include "itkImageFileReader.h"
#include "itkTransformFileWriter.h"
#include "itkAffineTransform.h"

#include "itkPluginUtilities.h"

#include "Calibration.h"
#include <ZFrameCalibrationCLP.h>


using namespace std;

int main( int argc, char * argv[] )
{
    PARSE_ARGS;
    
    const unsigned int Dimension = 3;
    
    typedef short PixelType;

    typedef itk::Image<PixelType, Dimension> ImageType;
    typedef itk::ImageFileReader<ImageType> ReaderType;
    ReaderType::Pointer reader = ReaderType::New();
    
    typedef itk::Matrix<double, 4, 4> MatrixType;
    
    reader->SetFileName(inputVolume.c_str());
    reader->Update();
    
    ImageType::Pointer image = reader->GetOutput();
    
    typedef ImageType::SizeType Size3D;
    Size3D dimensions = image->GetLargestPossibleRegion().GetSize();
    
    ImageType::DirectionType itkDirections = image->GetDirection();
    ImageType::PointType itkOrigin = image->GetOrigin();
    ImageType::SpacingType itkSpacing = image->GetSpacing();
    
    double origin[3] = {itkOrigin[0], itkOrigin[1], itkOrigin[2]};
    double spacing[3] = {itkSpacing[0], itkSpacing[1], itkSpacing[2]};
    double directions[3][3] = {{1.0,0.0,0.0},{0.0,1.0,0.0},{0.0,0.0,1.0}};
    for (unsigned int col=0; col<3; col++)
        for (unsigned int row=0; row<3; row++)
            directions[row][col] = itkDirections[row][col];
    
    MatrixType rtimgTransform;
    rtimgTransform.SetIdentity();
    
    int row, col;
    for(row=0; row<3; row++)
    {
        for(col=0; col<3; col++)
            rtimgTransform[row][col] = spacing[col] * directions[row][col];
        rtimgTransform[row][3] = origin[row];
    }
    
    //  LPS (ITK)to RAS (Slicer) transform matrix
    MatrixType lps2RasTransformMatrix;
    lps2RasTransformMatrix.SetIdentity();
    lps2RasTransformMatrix[0][0] = -1.0;
    lps2RasTransformMatrix[1][1] = -1.0;
    lps2RasTransformMatrix[2][2] =  1.0;
    lps2RasTransformMatrix[3][3] =  1.0;
    
    MatrixType imageToWorldTransform;
    imageToWorldTransform = lps2RasTransformMatrix * rtimgTransform;
    
    // Convert image positiona and orientation to zf::Matrix4x4
    zf::Matrix4x4 imageTransform;
    imageTransform[0][0] = imageToWorldTransform[0][0];
    imageTransform[1][0] = imageToWorldTransform[1][0];
    imageTransform[2][0] = imageToWorldTransform[2][0];
    imageTransform[0][1] = imageToWorldTransform[0][1];
    imageTransform[1][1] = imageToWorldTransform[1][1];
    imageTransform[2][1] = imageToWorldTransform[2][1];
    imageTransform[0][2] = imageToWorldTransform[0][2];
    imageTransform[1][2] = imageToWorldTransform[1][2];
    imageTransform[2][2] = imageToWorldTransform[2][2];
    imageTransform[0][3] = imageToWorldTransform[0][3];
    imageTransform[1][3] = imageToWorldTransform[1][3];
    imageTransform[2][3] = imageToWorldTransform[2][3];


    MatrixType ZFrameBaseOrientation;
    ZFrameBaseOrientation.SetIdentity();
    
    // ZFrame base orientation
    zf::Matrix4x4 ZmatrixBase;
    ZmatrixBase[0][0] = (float) ZFrameBaseOrientation[0][0];
    ZmatrixBase[1][0] = (float) ZFrameBaseOrientation[1][0];
    ZmatrixBase[2][0] = (float) ZFrameBaseOrientation[2][0];
    ZmatrixBase[0][1] = (float) ZFrameBaseOrientation[0][1];
    ZmatrixBase[1][1] = (float) ZFrameBaseOrientation[1][1];
    ZmatrixBase[2][1] = (float) ZFrameBaseOrientation[2][1];
    ZmatrixBase[0][2] = (float) ZFrameBaseOrientation[0][2];
    ZmatrixBase[1][2] = (float) ZFrameBaseOrientation[1][2];
    ZmatrixBase[2][2] = (float) ZFrameBaseOrientation[2][2];
    ZmatrixBase[0][3] = (float) ZFrameBaseOrientation[0][3];
    ZmatrixBase[1][3] = (float) ZFrameBaseOrientation[1][3];
    ZmatrixBase[2][3] = (float) ZFrameBaseOrientation[2][3];
    
    // Convert Base Matrix to quaternion
    float ZquaternionBase[4];
    zf::MatrixToQuaternion(ZmatrixBase, ZquaternionBase);
    
    // Set slice range
    int range[2];
    range[0] = startSlice;
    range[1] = endSlice;
    
    float Zposition[3];
    float Zorientation[4];
    
    // Call Z-frame registration
    zf::Calibration * calibration;
    calibration = new zf::Calibration();
    
    int dim[3];
    dim[0] = dimensions[0];
    dim[1] = dimensions[1];
    dim[2] = dimensions[2];
    
    calibration->SetInputImage(image->GetBufferPointer(), dim, imageTransform);
    calibration->SetOrientationBase(ZquaternionBase);
    int r = calibration->Register(range, Zposition, Zorientation);
    
    delete calibration;
    
    cout << r << endl;
    
    if (r)
    {
        // Convert quaternion to matrix
        zf::Matrix4x4 matrix;
        zf::QuaternionToMatrix(Zorientation, matrix);

        MatrixType zMatrix;
        zMatrix.SetIdentity();
        zMatrix[0][0] = matrix[0][0];
        zMatrix[1][0] = matrix[1][0];
        zMatrix[2][0] = matrix[2][0];
        zMatrix[0][1] = matrix[0][1];
        zMatrix[1][1] = matrix[1][1];
        zMatrix[2][1] = matrix[2][1];
        zMatrix[0][2] = matrix[0][2];
        zMatrix[1][2] = matrix[1][2];
        zMatrix[2][2] = matrix[2][2];
        zMatrix[0][3] = Zposition[0];
        zMatrix[1][3] = Zposition[1];
        zMatrix[2][3] = Zposition[2];

        cout << "RAS Transformation Matrix:" << endl;
        cout << zMatrix << endl;
        
        zMatrix = zMatrix * lps2RasTransformMatrix;
        zMatrix = (MatrixType)zMatrix.GetInverse() * lps2RasTransformMatrix;

        
        typedef itk::Matrix<double, 3, 3> TransformMatrixType;
        TransformMatrixType lpsTransformMatrix;
        lpsTransformMatrix.SetIdentity();
        lpsTransformMatrix[0][0] = zMatrix[0][0];
        lpsTransformMatrix[1][0] = zMatrix[1][0];
        lpsTransformMatrix[2][0] = zMatrix[2][0];
        lpsTransformMatrix[0][1] = zMatrix[0][1];
        lpsTransformMatrix[1][1] = zMatrix[1][1];
        lpsTransformMatrix[2][1] = zMatrix[2][1];
        lpsTransformMatrix[0][2] = zMatrix[0][2];
        lpsTransformMatrix[1][2] = zMatrix[1][2];
        lpsTransformMatrix[2][2] = zMatrix[2][2];
        
        typedef itk::AffineTransform<double> RegistrationTransformType;
        RegistrationTransformType::OutputVectorType translation;
        translation[0] = zMatrix[0][3];
        translation[1] = zMatrix[1][3];
        translation[2] = zMatrix[2][3];
        
        typedef itk::AffineTransform<double, 3> TransformType;
        TransformType::Pointer transform = TransformType::New();
        transform->SetMatrix(lpsTransformMatrix);
        transform->SetTranslation(translation);
        
        if (outputTransform != "")
        {
            itk::TransformFileWriter::Pointer markerTransformWriter = itk::TransformFileWriter::New();
            markerTransformWriter->SetInput(transform);
            markerTransformWriter->SetFileName(outputTransform.c_str());
            try
            {
                markerTransformWriter->Update();
            }
            catch (itk::ExceptionObject &err)
            {
                std::cerr << err << std::endl;
                return EXIT_FAILURE ;
            }
            
        }
    }
    
    return EXIT_SUCCESS;
}
