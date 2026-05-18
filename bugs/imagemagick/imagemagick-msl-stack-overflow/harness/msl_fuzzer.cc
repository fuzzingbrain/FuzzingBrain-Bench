#include <cstdint>
#include <Magick++/Blob.h>
#include <Magick++/Image.h>
#include "utils.cc"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size)
{
  if (IsInvalidSize(Size))
    return(0);
  try
  {
    const Magick::Blob blob(Data, Size);
    Magick::Image image;
    image.magick("MSL");
    image.fileName("MSL:");
    image.read(blob);
  }
  catch (Magick::Exception)
  {
  }
  return(0);
}
