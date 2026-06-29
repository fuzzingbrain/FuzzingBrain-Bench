// DCM decoder harness — AGF/O2Lab discovery path for CVE-2026-49218.
// Exercises ReadDCMImage via BlobToImage on raw bytes (dcm: coder).
#include <cassert>
#include <cstdint>

#include "MagickCore/MagickCore.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
  ImageInfo *image_info;
  ExceptionInfo *exception;
  Image *images;

  if (size < 16)
    return 0;

  MagickCoreGenesis((char *)"dcm_fuzzer", MagickFalse);
  image_info=AcquireImageInfo();
  exception=AcquireExceptionInfo();
  (void) FormatLocaleString(image_info->filename, MagickPathExtent, "dcm:");
  images=BlobToImage(image_info, data, size, exception);
  if (images != (Image *) NULL)
  {
    Image *p;
    for (p=images; p != (Image *) NULL; p=GetNextImageInList(p))
    {
      assert((p->columns != 0) && (p->rows != 0));
    }
    images=DestroyImageList(images);
  }
  exception=DestroyExceptionInfo(exception);
  image_info=DestroyImageInfo(image_info);
  MagickCoreTerminus();
  return 0;
}
