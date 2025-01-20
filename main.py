import json

import requests
from bilibili_api.search import SearchObjectType
from bs4 import BeautifulSoup
from bilibili_api import search, sync
from bilibili_api import Credential
import asyncio
from bilibili_api import video, Credential, HEADERS
import httpx
import os
from bilibili_api import settings



# FFMPEG 路径，查看：http://ffmpeg.org/
FFMPEG_PATH = "ffmpeg"


#发送请求获取报文
def get_search_result():


    # print(sync(credential.check_refresh()))
    # return sync(search.search("刀哥"))

    return sync(search.search_by_type("刀哥", search_type=SearchObjectType.VIDEO, page_size=50))


#解析json,拆分出视频地址
def anay_search_result(result_json):
    #print(result_json)

    # result_json = json.load(search_result)
    _video_arr=[]

    if "result" in result_json:
        for video_info in result_json.get("result"):
            title = video_info["title"]
            url = video_info["arcurl"]
            aid = video_info["aid"]
            _video_arr.append(aid)
            #print(title, url)
    return _video_arr


async def download_url(url: str, out: str, info: str):
    # 下载函数
    async with httpx.AsyncClient(headers=HEADERS) as sess:
        resp = await sess.get(url)
        length = resp.headers.get('content-length')
        with open(out, 'wb') as f:
            process = 0
            for chunk in resp.iter_bytes(1024):
                if not chunk:
                    break

                process += len(chunk)
                print(f'下载 {info} {process} / {length}')
                f.write(chunk)


#用arr下载视频
def download_video(video_arr):
    print(video_arr)

    credential = Credential(sessdata="357a3d5f%2C1752654708%2C332e2%2A12CjDWQ0b0DFAYvwOtUPkvbK4qy6-WKS6zjgb_jcHs_ic7pAjKXmshQygSQr-Rj7xe0mMSVnBiamx3VFgzb0FFUnJqMVpwNlJjbks2aFFvUDJXcW1pb25MNVVLUk1kUHRwOGlTVUI3V2tjYVpaR3VOMFpkbTJBRHExcGxQM3RxQVhZS0FZbzZuRkNnIIEC", bili_jct="e212cd205689d97f225a3ee1fea63400", buvid3="5E7F34AF-C92A-A3EC-B86E-30DE5EEA102053628infoc",dedeuserid="2045975", ac_time_value="7b0b7c2ce8653173339fe0780f3bd712")
    v = video.Video(aid=video_arr[0], credential=credential)
    # 获取视频下载链接
    download_url_data = sync(v.get_download_url(0))
    # 解析视频下载信息
    detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
    streams = detecter.detect_best_streams()
    # 有 MP4 流 / FLV 流两种可能
    if detecter.check_flv_stream() == True:
        # FLV 流下载
        sync(download_url(streams[0].url, "flv_temp.flv", "FLV 音视频流"))
        # 转换文件格式
        os.system(f'{FFMPEG_PATH} -i flv_temp.flv video.mp4')
        # 删除临时文件
        os.remove("flv_temp.flv")
    else:
        # MP4 流下载
        sync(download_url(streams[0].url, "video_temp.m4s", "视频流"))
        sync(download_url(streams[1].url, "audio_temp.m4s", "音频流"))
        # 混流
        os.system(f'{FFMPEG_PATH} -y -i video_temp.m4s -i audio_temp.m4s -vcodec copy -acodec copy video.mp4')
        # 删除临时文件
        os.remove("video_temp.m4s")
        os.remove("audio_temp.m4s")

    print('已下载为：video.mp4')


if __name__ == "__main__":
    settings.request_log = True

    search_result = get_search_result()

    video_arr = anay_search_result(search_result)

    download_video(video_arr)