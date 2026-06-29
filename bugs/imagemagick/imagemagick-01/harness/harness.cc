#include <algorithm>
#include <cstdint>
#include <cstddef>
#include <string>

#include <Magick++/Functions.h>

#include "utils.cc"

namespace
{
class ByteReader
{
public:
  ByteReader(const uint8_t *data,size_t size) : data_(data), size_(size), pos_(0) {}

  uint8_t GetByte()
  {
    if (pos_ >= size_)
      return(0);
    return(data_[pos_++]);
  }

  size_t remaining() const
  {
    return(pos_ < size_ ? size_ - pos_ : 0);
  }

private:
  const uint8_t *data_;
  size_t size_;
  size_t pos_;
};

static void AppendNumber(std::string *out,const size_t value)
{
  out->append(std::to_string(static_cast<unsigned long long>(value)));
}

static std::string MakeValue(ByteReader *reader,const bool force_finite)
{
  const uint8_t selector=reader->GetByte();
  if (!force_finite)
    {
      if ((selector % 11) == 0)
        return("nan");
      if ((selector % 11) == 1)
        return("-");
    }

  const int integer=static_cast<int>(reader->GetByte() % 41) - 20;
  const unsigned int fraction=reader->GetByte() % 100;
  std::string value=std::to_string(integer);
  if ((selector & 1) != 0)
    {
      value.push_back('.');
      if (fraction < 10)
        value.push_back('0');
      value.append(std::to_string(fraction));
    }
  return(value);
}

static void AppendUserKernel(std::string *out,ByteReader *reader)
{
  const uint8_t flags=reader->GetByte();
  size_t width=1 + (reader->GetByte() % 5);
  size_t height=1 + (reader->GetByte() % 5);
  const uint8_t rotation=flags % 5;

  /* Kernel rotation expansion is most meaningful for 3x3 kernels. */
  if (rotation != 0)
    {
      width=3;
      height=3;
    }

  AppendNumber(out,width);
  out->push_back('x');
  AppendNumber(out,height);

  if ((flags & 0x80) != 0)
    {
      out->push_back('+');
      AppendNumber(out,reader->GetByte() % width);
      out->push_back('+');
      AppendNumber(out,reader->GetByte() % height);
    }

  if (rotation == 1)
    out->push_back('@');
  else if (rotation == 2)
    out->push_back('>');
  else if (rotation == 3)
    out->push_back('<');

  out->push_back(':');
  const size_t count=width*height;
  for (size_t i=0; i < count; i++)
    {
      if (i != 0)
        out->push_back((reader->GetByte() & 1) != 0 ? ',' : ' ');
      out->append(MakeValue(reader,i == 0));
    }
}

static std::string MakeUserKernelList(ByteReader *reader)
{
  std::string result;
  const size_t kernels=1 + (reader->GetByte() % 3);
  if ((reader->GetByte() & 1) != 0)
    result.push_back(';');
  for (size_t i=0; i < kernels; i++)
    {
      if (i != 0)
        result.append((reader->GetByte() & 1) != 0 ? "; " : ";");
      AppendUserKernel(&result,reader);
    }
  if ((reader->GetByte() & 1) != 0)
    result.push_back(';');
  return(result);
}

static std::string MakeOldStyleKernel(ByteReader *reader)
{
  static const size_t counts[] = { 9, 25, 49 };
  const size_t count=counts[reader->GetByte() % (sizeof(counts)/sizeof(counts[0]))];
  std::string result;
  if ((reader->GetByte() & 1) != 0)
    result.push_back('\'');
  for (size_t i=0; i < count; i++)
    {
      if (i != 0)
        result.push_back((reader->GetByte() & 1) != 0 ? ',' : ' ');
      result.append(MakeValue(reader,i == 0));
    }
  if ((reader->GetByte() & 1) != 0)
    result.push_back('\'');
  return(result);
}

static std::string MakeNamedKernelList(ByteReader *reader)
{
  static const char *names[] = {
    "Unity", "Gaussian", "DoG", "LoG", "Blur", "Comet", "Binomial",
    "Laplacian", "Sobel", "FreiChen", "Roberts", "Prewitt", "Compass",
    "Kirsch", "Diamond", "Square", "Rectangle", "Octagon", "Disk",
    "Plus", "Cross", "Ring", "Peaks", "Edges", "Corners", "Diagonals",
    "LineEnds", "LineJunctions", "Ridges", "ConvexHull", "ThinSe",
    "Skeleton", "Chebyshev", "Manhattan", "Octagonal", "Euclidean"
  };

  std::string result;
  const size_t kernels=1 + (reader->GetByte() % 3);
  for (size_t i=0; i < kernels; i++)
    {
      if (i != 0)
        result.push_back(';');

      result.append(names[reader->GetByte() % (sizeof(names)/sizeof(names[0]))]);
      const uint8_t form=reader->GetByte() % 4;
      if (form != 0)
        {
          const size_t a=reader->GetByte() % 8;
          const size_t b=reader->GetByte() % 8;
          result.push_back(':');
          AppendNumber(&result,a);
          if (form >= 2)
            {
              result.push_back('x');
              AppendNumber(&result,b);
            }
          if (form == 3)
            {
              const size_t x=(a == 0 ? 0 : reader->GetByte() % a);
              const size_t y=(b == 0 ? 0 : reader->GetByte() % b);
              result.push_back('+');
              AppendNumber(&result,x);
              result.push_back('+');
              AppendNumber(&result,y);
              switch (reader->GetByte() % 4)
                {
                  case 1: result.push_back('@'); break;
                  case 2: result.push_back('>'); break;
                  case 3: result.push_back('<'); break;
                  default: break;
                }
            }
        }
    }
  return(result);
}

static std::string MakeSanitizedRawString(const uint8_t *data,const size_t size)
{
  static const char alphabet[] =
    "0123456789abcdfghijklmnopqrstuvwxyzABCDFGHIJKLMNOPQRSTUVWXYZ:;,xX+- .@><'%";

  const size_t max_length=std::min<size_t>(size,512);
  std::string result;
  result.reserve(max_length);
  unsigned int digit_run=0;
  for (size_t i=0; i < max_length; i++)
    {
      char c=alphabet[data[i] % (sizeof(alphabet)-1)];
      if ((c >= '0') && (c <= '9'))
        {
          if (digit_run >= 2)
            {
              c=',';
              digit_run=0;
            }
          else
            digit_run++;
        }
      else
        digit_run=0;

      if ((result.empty()) && (c == '@'))
        c=' ';
      result.push_back(c);
    }
  return(result);
}
}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data,size_t Size)
{
  if (Size > 8192)
    return(0);

  ByteReader reader(Data,Size);
  const uint8_t mode=(Size == 0) ? 0 : (reader.GetByte() % 5);

  std::string kernel_string;
  const char *kernel_cstr=nullptr;
  if (mode == 1)
    {
      kernel_string=MakeUserKernelList(&reader);
      kernel_cstr=kernel_string.c_str();
    }
  else if (mode == 2)
    {
      kernel_string=MakeOldStyleKernel(&reader);
      kernel_cstr=kernel_string.c_str();
    }
  else if (mode == 3)
    {
      kernel_string=MakeNamedKernelList(&reader);
      kernel_cstr=kernel_string.c_str();
    }
  else if (mode == 4)
    {
      const size_t offset=(Size == 0) ? 0 : 1;
      kernel_string=MakeSanitizedRawString(Data + offset,Size - offset);
      kernel_cstr=kernel_string.c_str();
    }

  MagickCore::ExceptionInfo *exception=MagickCore::AcquireExceptionInfo();
  if (exception == nullptr)
    return(0);

  MagickCore::KernelInfo *kernel=MagickCore::AcquireKernelInfo(kernel_cstr,exception);
  if (kernel != nullptr)
    kernel=MagickCore::DestroyKernelInfo(kernel);

  exception=MagickCore::DestroyExceptionInfo(exception);
  return(0);
}
