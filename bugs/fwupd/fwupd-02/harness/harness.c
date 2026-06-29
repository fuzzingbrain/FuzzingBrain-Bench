#include <glib.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include "fwupdplugin.h"
#include "fu-logitech-bulkcontroller-device.h"

static const guint8 *fuzz_data;
static gsize fuzz_size;

static void
fu_usb_device_class_init(FuUsbDeviceClass *klass)
{
	(void)klass;
}

static void
fu_usb_device_init(FuUsbDevice *self)
{
	(void)self;
}

G_DEFINE_TYPE(FuUsbDevice, fu_usb_device, FU_TYPE_UDEV_DEVICE)

void
fu_usb_device_add_interface(FuUsbDevice *device, guint8 number)
{
	(void)device;
	(void)number;
}

void
fu_usb_device_set_claim_retry_count(FuUsbDevice *self, guint claim_retry_count)
{
	(void)self;
	(void)claim_retry_count;
}

GPtrArray *
fu_usb_device_get_interfaces(FuUsbDevice *self, GError **error)
{
	(void)self;
	(void)error;
	return g_ptr_array_new();
}

guint8
fu_usb_interface_get_class(FuUsbInterface *intf)
{
	(void)intf;
	return 0;
}

guint8
fu_usb_interface_get_protocol(FuUsbInterface *intf)
{
	(void)intf;
	return 0;
}

guint8
fu_usb_interface_get_subclass(FuUsbInterface *intf)
{
	(void)intf;
	return 0;
}

GPtrArray *
fu_usb_interface_get_endpoints(FuUsbInterface *intf)
{
	(void)intf;
	return g_ptr_array_new();
}

guint8
fu_usb_interface_get_number(FuUsbInterface *intf)
{
	(void)intf;
	return 0;
}

guint8
fu_usb_endpoint_get_address(FuUsbEndpoint *ep)
{
	(void)ep;
	return 0;
}

void
fu_logitech_bulkcontroller_fuzz_set_input(const guint8 *data, gsize size)
{
	fuzz_data = data;
	fuzz_size = size;
}

gboolean
__wrap_fu_usb_device_bulk_transfer(FuUsbDevice *self,
				   guint8 endpoint,
				   guint8 *data,
				   gsize length,
				   gsize *actual_length,
				   guint timeout,
				   GCancellable *cancellable,
				   GError **error)
{
	gsize copy = 0;

	(void)self;
	(void)endpoint;
	(void)timeout;
	(void)cancellable;
	(void)error;

	if (fuzz_data != NULL)
		copy = MIN(fuzz_size, length);
	if (data != NULL && copy > 0)
		memcpy(data, fuzz_data, copy);
	if (actual_length != NULL)
		*actual_length = copy;
	return TRUE;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
	g_autoptr(FuLogitechBulkcontrollerDevice) dev = NULL;
	g_autoptr(GError) error = NULL;
	g_autoptr(GByteArray) response = NULL;

	if (size < 12)
		return 0;

	dev = g_object_new(FU_TYPE_LOGITECH_BULKCONTROLLER_DEVICE, NULL);
	response = fu_logitech_bulkcontroller_device_sync_wait_any_fuzz(dev,
									data,
									size,
									&error);
	(void)response;
	return 0;
}
