
#include "itkTransformFileWriter.h"

#include "itkImage.h"
#include "itkImageFileReader.h"
#include "itkCastImageFilter.h"
#include "itkPluginUtilities.h"

#include "Calibration.h"
#include <ZFrameCalibrationCLP.h>


using namespace std;

namespace {

    
template<class T> int DoIt( int argc, char * argv[], T )
{
    PARSE_ARGS;
    
    const unsigned int Dimension = 3;
    
    typedef float PixelType;

    typedef itk::Image<PixelType, Dimension> ImageType;
    typedef itk::ImageFileReader<ImageType> ReaderType;
    typename ReaderType::Pointer reader = ReaderType::New();
    
    typedef itk::Matrix<double, 4, 4> MatrixType;

    reader->SetFileName(inputVolume.c_str());
    reader->Update();
    
    typedef itk::Image<short, Dimension>  ShortImageType;
    typedef itk::CastImageFilter<ImageType, ShortImageType> CastFilterType;
    CastFilterType::Pointer castFilter = CastFilterType::New();
    castFilter->SetInput(reader->GetOutput());

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
    imageToWorldTransform.SetIdentity();
    imageToWorldTransform = imageToWorldTransform * lps2RasTransformMatrix;
    imageToWorldTransform = imageToWorldTransform * rtimgTransform;

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
    
    ShortImageType::Pointer shortImage = castFilter->GetOutput();
    short* inputImage = (short*)shortImage.GetPointer();
    
    float Zposition[3];
    float Zorientation[4];
    
    // Call Z-frame registration
    zf::Calibration * calibration;
    calibration = new zf::Calibration();
    
    int dim[3];
    dim[0] = dimensions[0];
    dim[1] = dimensions[1];
    dim[2] = dimensions[2];
    
    calibration->SetInputImage(inputImage, dim, imageTransform);
    calibration->SetOrientationBase(ZquaternionBase);
    int r = calibration->Register(range, Zposition, Zorientation);
    
    delete calibration;
    
    cout << r << endl;
    
    if (r)
    {
        // Convert quaternion to matrix
        zf::Matrix4x4 matrix;
        zf::QuaternionToMatrix(Zorientation, matrix);
        matrix[0][3] = Zposition[0];
        matrix[1][3] = Zposition[1];
        matrix[2][3] = Zposition[2];
        
        std::cerr << "Result matrix:" << std::endl;
        zf::PrintMatrix(matrix);

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
        zMatrix[0][3] = matrix[0][3];
        zMatrix[1][3] = matrix[1][3];
        zMatrix[2][3] = matrix[2][3];
        
    }
    
    return EXIT_SUCCESS;
}
    
}

int main( int argc, char * argv[] )
{
    PARSE_ARGS;
    
    itk::ImageIOBase::IOPixelType pixelType;
    itk::ImageIOBase::IOComponentType componentType;
    
    try
    {
        itk::GetImageType (inputVolume, pixelType, componentType);
        
        // This filter handles all types on input, but only produces
        // signed types
        switch (componentType)
        {
            case itk::ImageIOBase::UCHAR:
                return DoIt( argc, argv, static_cast<unsigned char>(0));
                break;
            case itk::ImageIOBase::CHAR:
                return DoIt( argc, argv, static_cast<char>(0));
                break;
            case itk::ImageIOBase::USHORT:
                return DoIt( argc, argv, static_cast<unsigned short>(0));
                break;
            case itk::ImageIOBase::SHORT:
                return DoIt( argc, argv, static_cast<short>(0));
                break;
            case itk::ImageIOBase::UINT:
                return DoIt( argc, argv, static_cast<unsigned int>(0));
                break;
            case itk::ImageIOBase::INT:
                return DoIt( argc, argv, static_cast<int>(0));
                break;
            case itk::ImageIOBase::ULONG:
                return DoIt( argc, argv, static_cast<unsigned long>(0));
                break;
            case itk::ImageIOBase::LONG:
                return DoIt( argc, argv, static_cast<long>(0));
                break;
            case itk::ImageIOBase::FLOAT:
                return DoIt( argc, argv, static_cast<float>(0));
                break;
            case itk::ImageIOBase::DOUBLE:
                return DoIt( argc, argv, static_cast<double>(0));
                break;
            case itk::ImageIOBase::UNKNOWNCOMPONENTTYPE:
            default:
                std::cout << "unknown component type" << std::endl;
                break;
        }
    }
    
    catch( itk::ExceptionObject &excep)
    {
        std::cerr << argv[0] << ": exception caught !" << std::endl;
        std::cerr << excep << std::endl;
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
