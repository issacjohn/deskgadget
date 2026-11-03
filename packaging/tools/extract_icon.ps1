param(
  [Parameter(Mandatory = $true)][string]$src,
  [Parameter(Mandatory = $true)][string]$out
)

# Extracts a 256px icon (with alpha) from a .lnk, .exe or any shell item.
Add-Type -AssemblyName System.Drawing

$code = @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

public static class IconGrab
{
    [StructLayout(LayoutKind.Sequential)]
    public struct SIZE { public int cx; public int cy; }

    [Flags]
    public enum SIIGBF { RESIZETOFIT = 0, BIGGERSIZEOK = 1, MEMORYONLY = 2, ICONONLY = 4, THUMBNAILONLY = 8, INCACHEONLY = 16 }

    [ComImport, Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItemImageFactory
    {
        void GetImage(SIZE size, SIIGBF flags, out IntPtr phbm);
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateItemFromParsingName(string path, IntPtr pbc, ref Guid riid,
        [MarshalAs(UnmanagedType.Interface)] out object shellItem);

    [StructLayout(LayoutKind.Sequential)]
    struct BITMAP
    {
        public int bmType, bmWidth, bmHeight, bmWidthBytes;
        public ushort bmPlanes, bmBitsPixel;
        public IntPtr bmBits;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct BITMAPINFOHEADER
    {
        public int biSize, biWidth, biHeight;
        public short biPlanes, biBitCount;
        public int biCompression, biSizeImage, biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant;
    }

    [DllImport("gdi32.dll")] static extern int GetObject(IntPtr h, int c, out BITMAP pv);
    [DllImport("gdi32.dll")] static extern IntPtr CreateCompatibleDC(IntPtr hdc);
    [DllImport("gdi32.dll")] static extern bool DeleteDC(IntPtr hdc);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr o);
    [DllImport("gdi32.dll")]
    static extern int GetDIBits(IntPtr hdc, IntPtr hbm, uint start, uint lines, byte[] bits,
        ref BITMAPINFOHEADER header, uint usage);

    static Bitmap ToBitmap(IntPtr hbm)
    {
        BITMAP bm;
        if (GetObject(hbm, Marshal.SizeOf(typeof(BITMAP)), out bm) == 0) return null;
        int w = bm.bmWidth;
        int h = Math.Abs(bm.bmHeight);
        var header = new BITMAPINFOHEADER
        {
            biSize = Marshal.SizeOf(typeof(BITMAPINFOHEADER)),
            biWidth = w,
            biHeight = -h,
            biPlanes = 1,
            biBitCount = 32,
            biCompression = 0
        };
        int stride = w * 4;
        var buffer = new byte[stride * h];
        IntPtr hdc = CreateCompatibleDC(IntPtr.Zero);
        GetDIBits(hdc, hbm, 0, (uint)h, buffer, ref header, 0);
        DeleteDC(hdc);

        var bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        var data = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
        Marshal.Copy(buffer, 0, data.Scan0, buffer.Length);
        bmp.UnlockBits(data);
        return bmp;
    }

    public static bool Save(string path, string outPath, int size)
    {
        try
        {
            Guid iid = new Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b");
            object item;
            SHCreateItemFromParsingName(path, IntPtr.Zero, ref iid, out item);
            var factory = (IShellItemImageFactory)item;
            IntPtr hbm;
            factory.GetImage(new SIZE { cx = size, cy = size }, SIIGBF.BIGGERSIZEOK | SIIGBF.ICONONLY, out hbm);
            if (hbm != IntPtr.Zero)
            {
                using (Bitmap bmp = ToBitmap(hbm))
                {
                    if (bmp != null) bmp.Save(outPath, ImageFormat.Png);
                }
                DeleteObject(hbm);
                if (System.IO.File.Exists(outPath)) return true;
            }
        }
        catch { }

        try
        {
            using (var ico = Icon.ExtractAssociatedIcon(path))
            {
                if (ico == null) return false;
                using (var bmp = ico.ToBitmap()) bmp.Save(outPath, ImageFormat.Png);
                return true;
            }
        }
        catch { return false; }
    }
}
"@

try {
  Add-Type -TypeDefinition $code -ReferencedAssemblies System.Drawing -ErrorAction Stop
} catch {
  Write-Output "FAIL compile: $($_.Exception.Message)"
  exit 1
}

if (Test-Path $out) { Remove-Item $out -Force -ErrorAction SilentlyContinue }
if ([IconGrab]::Save($src, $out, 256)) {
  Write-Output "OK"
} else {
  Write-Output "FAIL"
}
