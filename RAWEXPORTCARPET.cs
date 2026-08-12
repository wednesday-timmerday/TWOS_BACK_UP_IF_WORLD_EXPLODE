case SerializeModes.Export:
if (obj is MapScene.Room)
{
MapScene.Room Room = obj as MapScene.Room;
string RoomText = "";

```
    RoomText += "TOTAL_LAYERS = 1\n";
    RoomText += "TILE_W = 8\nTILE_H = 8";
    RoomText += $"WORLD_W = {Room.width}\n";
    RoomText += $"WORLD_H = {Room.height}\n";
    RoomText += "LAYER1:\n";

    TestEntity entity = Engine.Scene.Tracker.GetEntity<TestEntity>();

    if (entity != null)
    {
        string Map = "";

        // Row-major order to match the loader:
        // y first, then x
        for (int y = 0; y < Room.map.Rows; y++)
        {
            for (int x = 0; x < Room.map.Columns; x++)
            {
                char car = Room.map[x, y];

                if (car != '0')
                {
                    MTexture tile = GFX.FGAutotiler.Tilesets[car].Texture;
                    int[] tilesD = entity.tiles.TilesD[x, y];

                    int tileD = tile.Width / 8 * tilesD[1] + tilesD[0];

                    RoomText += $"${car}{tileD}";
                }
                else
                {
                    RoomText += "$0";
                }
            }
        }
    }

    byte[] textBytes = Encoding.UTF8.GetBytes(RoomText);
    fileStream.Write(textBytes, 0, textBytes.Length);
}
break;
```
