using System;
using System.IO;
using System.Drawing;
using System.Drawing.Imaging;
using System.Collections.Generic;
namespace NasdaqQDII {
    internal static class BuildAssets {
        static void Main(string[] args) {
            int[] sizes={16,24,32,48,64,128,256};var images=new List<byte[]>();
            foreach(int size in sizes) using(var image=Icons.Draw(size,Color.FromArgb(75,215,173))) using(var stream=new MemoryStream()) {image.Save(stream,ImageFormat.Png);images.Add(stream.ToArray());}
            using(var writer=new BinaryWriter(File.Create(args[0]))) {
                writer.Write((short)0);writer.Write((short)1);writer.Write((short)sizes.Length);int offset=6+16*sizes.Length;
                for(int i=0;i<sizes.Length;i++) {writer.Write((byte)(sizes[i]==256?0:sizes[i]));writer.Write((byte)(sizes[i]==256?0:sizes[i]));writer.Write((byte)0);writer.Write((byte)0);writer.Write((short)1);writer.Write((short)32);writer.Write(images[i].Length);writer.Write(offset);offset+=images[i].Length;}
                foreach(var image in images) writer.Write(image);
            }
        }
    }
}
