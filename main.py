import os
import re
import subprocess
import uuid
import logging

import httpx
from bilibili_api import search, sync
from bilibili_api import video, Credential, HEADERS
from bilibili_api.search import SearchObjectType
from retry import retry

FFMPEG_PATH = "ffmpeg"

DEFAULT_PAGE_SIZE = 20

logging.basicConfig(filename='biliThief.log', level=logging.DEBUG,
                    format='%(asctime)s:%(levelname)s:%(message)s')


# 初始化控制台 用户选择菜单
def init_menu_command():
    logging.info('--Start--')
    print("************************************")
    print("****        Bili  Thief         ****")
    print("****        2025  01  21        ****")
    print("************************************")
    print("[1] 查询并爬取")
    print("[2] 页面地址直接下载")
    print("请输入选项,1或2:")

    command = None
    while command is None:
        try:
            command = int(input())
        except:
            print("输入错误,请重新输入")

    logging.info('Command: ' + str(command))
    return command


# 初始化控制台
def get_user_search():
    print("请输入搜索词:")

    search_key = None
    while search_key is None:
        try:
            search_key = str(input())
        except:
            print("输入错误,请重新输入")
    logging.info('SearchKey: ' + search_key)
    return search_key


# 发送请求获取报文
@retry(exceptions=Exception, delay=2, jitter=(1, 3), tries=3)
def get_search_result_raw(_user_search_word, page_num=1):
    logging.info('fetch-bili-data: ' + _user_search_word + ' page: ' + str(page_num))
    return sync(
        search.search_by_type(_user_search_word, search_type=SearchObjectType.VIDEO, page_size=DEFAULT_PAGE_SIZE,
                              page=page_num))


# 根据首页结果数交互获取用户要下载的条数
def get_user_download_size(_search_result_raw_json):
    if "page" in _search_result_raw_json and "pagesize" in _search_result_raw_json and "numResults" in _search_result_raw_json and "numPages" in _search_result_raw_json:
        print("[√] 搜索结果：=============================")
        print("视频总数：" + str(_search_result_raw_json.get("numResults")))
        print("视频页数(*每页" + str(DEFAULT_PAGE_SIZE) + ")：" + str(_search_result_raw_json.get("numPages")))
        print("请输入要下载的视频数量,0表示第一页所有:")

        user_count = None
        while user_count is None:
            try:
                user_count = int(input())
            except:
                print("输入错误,请重新输入")
        if user_count == 0:
            user_count = DEFAULT_PAGE_SIZE
        if user_count > _search_result_raw_json.get("numResults"):
            user_count = _search_result_raw_json.get("numResults")
        if user_count > 0:
            return user_count
        print("请勿输入负数!无法上传!")
        return get_user_download_size(_search_result_raw_json)
    else:
        print("搜索结果参数错误,请联系开发")
        return -1
        # sys.exit()


# 解析json,拆分出视频地址
def get_full_video_list(user_download_size, result_json, user_search_word):
    _video_arr = []
    _full_video_arr = []

    if user_download_size <= DEFAULT_PAGE_SIZE:
        # 下载数量小于分页,已获取的页面全都下载就完事了
        if "result" in result_json:
            for full_video_info in result_json.get("result"):
                _full_video_arr.append(full_video_info)
                _video_arr = _full_video_arr[0:user_download_size]
        print("成功获取" + str(len(_video_arr)) + "个视频详细信息 =============================")
        return _video_arr
    else:
        # 计算总计页码
        target_page = int(user_download_size // DEFAULT_PAGE_SIZE)
        final_page_counts = 0

        if user_download_size % DEFAULT_PAGE_SIZE != 0:
            final_page_counts = user_download_size - (DEFAULT_PAGE_SIZE * target_page)
            target_page = target_page + 1

        # for 页码
        for i in range(1, target_page + 1):
            if i == 1:
                # 第一页最初请求过了,直接加
                if "result" in result_json:
                    for full_video_info in result_json.get("result"):
                        _video_arr.append(full_video_info)
                continue
            if i == target_page:
                # 获取最后一页
                _final_video_arr = []
                print("正在获取第" + str(i) + "页数据")
                result_json = get_search_result_raw(user_search_word, i)
                if "result" in result_json:
                    for full_video_info in result_json.get("result"):
                        _final_video_arr.append(full_video_info)
                    for i in range(final_page_counts):
                        _video_arr.append(_final_video_arr[i])
            else:
                # 中间的页码,全拿加到arr里
                print("正在获取第" + str(i) + "页数据")
                result_json = get_search_result_raw(user_search_word, i)
                if "result" in result_json:
                    for full_video_info in result_json.get("result"):
                        _video_arr.append(full_video_info)
        print("[√] 成功获取" + str(len(_video_arr)) + "个视频详细信息 =============================")
        return _video_arr


@retry(exceptions=Exception, delay=2, jitter=(1, 3), tries=3)
async def download_url(url: str, out: str, info: str):
    logging.info('download_url: ' + url + ' out: ' + out)
    # 下载函数
    async with httpx.AsyncClient(headers=HEADERS) as sess:
        resp = await sess.get(url)
        length = resp.headers.get('content-length')
        with open(out, 'wb') as f:
            process = 0
            for chunk in resp.iter_bytes(4096):
                if not chunk:
                    break

                process += len(chunk)
                # print(f'下载 {info} {process} / {length}')
                f.write(chunk)


# 获取用户下载路径
def get_user_download_dir_path():
    print("视频保存在磁盘根目录的 /BiliThief 文件夹内")
    print("请输入要保存在哪个磁盘盘符,输入CDEF等单个字母,默认D盘:")

    user_download_disk = None
    while user_download_disk is None:
        try:
            user_download_disk = str(input())
        except:
            print("输入错误,请重新输入")

    logging.info('userTargetDisk: ' + user_download_disk)
    if user_download_disk.isalpha() or user_download_disk == "":
        try:
            if user_download_disk == "":
                user_download_disk = "D"
            elif user_download_disk.upper() not in ["C", "D", "E", "F", "G", "H"]:
                user_download_disk = "D"
            os.makedirs(user_download_disk + ":/BiliThief/", exist_ok=True)
            print("[√] 视频将保存在: " + user_download_disk + ":/BiliThief/" + " =============================")
            logging.info('userTargetDir: ' + user_download_disk + ":/BiliThief/")
            return user_download_disk + ":/BiliThief/"
        except:
            print("磁盘盘符输入错误,请重新输入")
            logging.exception("磁盘盘符输入错误,请重新输入")
            return get_user_download_dir_path()
    else:
        print("输入错误,请重新输入")
        logging.exception("输入错误,请重新输入")
        return get_user_download_dir_path()
    pass


# 用arr下载视频
def download_video(video_arr, user_download_dir_path, avid_or_bvid=1):
    print("准备批量下载视频...")
    logging.info("--Start Download--")
    credential = Credential(
        sessdata="357a3d5f%2C1752654708%2C332e2%2A12CjDWQ0b0DFAYvwOtUPkvbK4qy6-WKS6zjgb_jcHs_ic7pAjKXmshQygSQr-Rj7xe0mMSVnBiamx3VFgzb0FFUnJqMVpwNlJjbks2aFFvUDJXcW1pb25MNVVLUk1kUHRwOGlTVUI3V2tjYVpaR3VOMFpkbTJBRHExcGxQM3RxQVhZS0FZbzZuRkNnIIEC",
        bili_jct="e212cd205689d97f225a3ee1fea63400", buvid3="5E7F34AF-C92A-A3EC-B86E-30DE5EEA102053628infoc",
        dedeuserid="2045975", ac_time_value="7b0b7c2ce8653173339fe0780f3bd712")

    item_index = 1
    for single_video in video_arr:
        try:
            print("[△] 正在下载视频: " + str(item_index) + " in " + str(len(video_arr)) + " =============================")
            logging.info(str(item_index) + "in total" + str(len(video_arr)))
            single_title = single_video.get('title').replace("</em>", "")
            single_title = single_title.replace("<em>", "")
            single_title = single_title.replace("<em>", "")
            single_title = single_title.replace("<em class=\"keyword\">", "")
            single_title = single_title.replace("em class=keyword", "")
            single_title = single_title.replace("&quot;", "")

            illegal_chars = r'[<>:"\\|?*]'
            single_title = re.sub(illegal_chars, '', single_title)

            print("[△] 正在下载视频: " + single_title)
            print("AID: " + str(single_video.get('aid')) + "     BVID: " + single_video.get('bvid'))
            print("时长: " + single_video.get('duration') + "(<10分钟的约下载3分内,10-60分的约下载5-8分钟,更长的视频约需要1/10的时间下载!!!请耐心等待!)")
            logging.info(single_title)
            logging.info(str(single_video.get('aid')))
            logging.info(single_video.get('bvid'))
            logging.info(single_video.get('duration'))

            if single_video.get('type') not in ["video"]:
                logging.info(single_video.get('type'))
                print("ERROR: 类型错误,将跳过该条目!")
                print("期望类型为: Video,该条目类型为: " + single_video.get('type'))
                continue

            v = None
            if avid_or_bvid == 1:
                logging.info("aid download")
                v = video.Video(aid=single_video.get('aid'), credential=credential)
            else:
                logging.info("bvid download")
                v = video.Video(bvid=single_video.get('bvid'), credential=credential)

            page_info = sync(v.get_pages())

            if len(page_info) > 1:
                print("视频存在多个分P,将分别下载!!!")

            for p_count in range(len(page_info)):
                if len(page_info) > 1:
                    print("正在下载分P: " + str(p_count + 1) + " in " + str(len(page_info)))

                # 获取视频下载链接
                download_url_data = sync(v.get_download_url(p_count))
                # 解析视频下载信息
                detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
                streams = detecter.detect_best_streams()
                # 有 MP4 流 / FLV 流两种可能
                if detecter.check_flv_stream() == True:
                    logging.info("flv")
                    # FLV 流下载
                    sync(download_url(streams[0].url, user_download_dir_path + "flv_temp.flv", "FLV 音视频流"))
                    # 转换文件格式
                    cmd = f'{FFMPEG_PATH} -y -i "' + user_download_dir_path + 'flv_temp.flv" -c copy "' + user_download_dir_path + single_title + "_" + str(
                        p_count) + '.mp4" '
                    logging.info(cmd)
                    # os.system(f'{FFMPEG_PATH} -y -i "' + user_download_dir_path + 'flv_temp.flv"  "' + user_download_dir_path + single_title + '.mp4" ')
                    subprocess.call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

                    # 删除临时文件
                    try:
                        os.remove(user_download_dir_path + "flv_temp.flv")
                    except:
                        logging.exception("delete tmp file error")
                else:
                    logging.info("m4s")
                    # MP4 流下载
                    sync(download_url(streams[0].url, user_download_dir_path + "video_temp.m4s", "视频流"))

                    is_has_voice = None
                    try:
                        sync(download_url(streams[1].url, user_download_dir_path + "audio_temp.m4s", "音频流"))
                        is_has_voice = True
                    except:
                        logging.exception("no voice")
                        is_has_voice = False
                    # 混流
                    # os.system(f'{FFMPEG_PATH} -y -i "' + user_download_dir_path + 'video_temp.m4s" -i "' + user_download_dir_path + 'audio_temp.m4s" -vcodec copy -acodec copy "' + user_download_dir_path + single_title + '.mp4" ')

                    if is_has_voice:
                        cmd = f'{FFMPEG_PATH} -y -i "' + user_download_dir_path + 'video_temp.m4s" -i "' + user_download_dir_path + 'audio_temp.m4s" -vcodec copy -acodec copy "' + user_download_dir_path + single_title + "_" + str(
                            p_count) + '.mp4" '
                        logging.info(cmd)
                    else:
                        print("[×] 该视频没有音频流")
                        cmd = f'{FFMPEG_PATH} -y -i "' + user_download_dir_path + 'video_temp.m4s"  -vcodec copy  "' + user_download_dir_path + single_title + "_" + str(
                            p_count) + '.mp4" '
                        logging.info(cmd)

                    subprocess.call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

                    # 删除临时文件
                    try:
                        os.remove(user_download_dir_path + "video_temp.m4s")
                        os.remove(user_download_dir_path + "audio_temp.m4s")
                    except:
                        logging.exception("delete tmp file error")
                        pass
                item_index = item_index + 1
                print('[√] 已下载：' + single_title + "_" + str(p_count) + " =============================")

        except:
            logging.exception("download error")


# 用户提供链接 直接下载视频
def user_download_link_video():
    # 用户输入盘符
    _user_download_dir_path = get_user_download_dir_path()
    logging.info('UserDownloadDir: ' + str(_user_download_dir_path))

    print("[△] 请确认视频地址为AV还是BV =============================")
    print("AV请选择1:(例如https://www.bilibili.com/video/av113859801122834)")
    print("BV请选择2:(例如https://www.bilibili.com/video/BV1Q7wpe2E45)")

    user_input_av_or_bv = None
    while user_input_av_or_bv is None:
        try:
            user_input_av_or_bv = int(input())
        except:
            print("输入错误,请重新输入")

    logging.info('UserAVOrBV: ' + str(user_input_av_or_bv))
    if user_input_av_or_bv == 2:
        print("[√] 是BV地址")
    else:
        print("[√] 是AV地址")
    print("[△] 请输入视频地址:")

    user_input_video_link = None
    while user_input_video_link is None:
        try:
            user_input_video_link = input()
        except:
            print("输入错误,请重新输入")

    logging.info('UserDownloadAddr: ' + user_input_video_link)
    _video_arr = []
    if user_input_av_or_bv == 2:
        split_arr = user_input_video_link.split("/")
        for item in split_arr:
            logging.info('item: ' + item)
            if item.startswith("bv") or item.startswith("BV"):
                bv_id = item.upper().replace("BV", "", 1)
                _video_arr.append({"type": "video", "aid": "---", "title": "a" + str(uuid.uuid4().hex), "bvid": bv_id,
                                   "duration": "99:99"})
                download_video(_video_arr, _user_download_dir_path, 2)
    else:
        split_arr = user_input_video_link.split("/")
        for item in split_arr:
            logging.info('item: ' + item)
            if item.startswith("av") or item.startswith("AV"):
                av_id = item.upper().replace("AV", "", 1)
                _video_arr.append(
                    {"type": "video", "aid": int(av_id), "title": "a" + str(uuid.uuid4().hex), "bvid": "---",
                     "duration": "99:99"})
                download_video(_video_arr, _user_download_dir_path, 1)

    print("[√] 下载已完成,可关闭此窗口......")
    logging.info('--DownloadSuccess--')
    input()


if __name__ == "__main__":
    # settings.request_log = True
    # 初始化
    user_command = init_menu_command()

    if user_command == 2:
        user_download_link_video()
    else:
        user_search_word = get_user_search()
        print("[√] 搜索词为: " + user_search_word + " =============================")
        print("搜索中......")
        # 获取第一页信息及用户输入下载信息
        search_result_raw_json = get_search_result_raw(user_search_word)
        # print(search_result_raw_json)

        user_download_size = get_user_download_size(search_result_raw_json)
        logging.info('UserDownloadSize: ' + str(user_download_size))
        if user_download_size > 0:
            print("[√] 计划下载视频数量为: " + str(user_download_size) + " =============================")
        # 用户输入盘符
        user_download_dir_path = get_user_download_dir_path()
        # 获取格式化好的视频信息列表
        video_arr = get_full_video_list(user_download_size, search_result_raw_json, user_search_word)
        # 根据视频信息列表下载视频
        download_video(video_arr, user_download_dir_path)
        print("[√] 批量下载已完成,可关闭此窗口......")
        logging.info('--SearchAndDownloadSuccess--')
        input()
