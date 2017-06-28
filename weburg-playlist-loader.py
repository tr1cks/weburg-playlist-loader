#!/usr/bin/env python3

import urllib.request
from argparse import ArgumentParser
from enum import Enum
from operator import attrgetter
from typing import List, Dict
from xml.etree.ElementTree import ElementTree


class SocketAddress(object):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def __repr__(self, *args, **kwargs):
        return "<SocketAddress address:{} port:{}>".format(self.host, self.port)

    def __str__(self, *args, **kwargs):
        return "{}:{}".format(self.host, self.port)


class Channel(object):
    def __init__(self, channel_id: int, name: str, address: SocketAddress):
        self.id = channel_id
        self.name = name
        # Адрес мультикаст группы
        self.address = address

    def __repr__(self, *args, **kwargs):
        return "<Channel id:{} name:{} address:{}>".format(self.id, self.name, self.address)


class ChannelGroup(object):
    def __init__(self, name: str, channels: List[Channel]):
        self.name = name
        self.channels = channels

    def __repr__(self, *args, **kwargs):
        return "<ChannelGroup name:{} channels:{}>".format(self.name, self.channels)


class PlaylistType(Enum):
    MULTICAST = 1
    UNICAST = 2


def write_playlist(filename: str, playlist_type: PlaylistType, groups: List[ChannelGroup], proxy_address: SocketAddress,
                   sort_by_name: bool):
    with open(filename, "w", encoding="utf-8") as filename:
        filename.write("#EXTM3U\n")

        for group in sorted(groups, key=attrgetter("name")) if sort_by_name else groups:
            for channel in sorted(group.channels, key=attrgetter("name")) if sort_by_name else group.channels:
                filename.write("#EXTINF:0 group-title=\"{}\",{}\n".format(group.name, channel.name))

                if playlist_type == PlaylistType.UNICAST:
                    filename.write("http://{}/udp/{}\n".format(proxy_address, channel.address))
                elif playlist_type == PlaylistType.MULTICAST:
                    filename.write("udp://@{}\n".format(channel.address))
                else:
                    raise Exception("Unknown playlist type: {}".format(playlist_type))


def fetch_xml_playlist(url: str) -> ElementTree:
    with urllib.request.urlopen(url) as xml:
        return ElementTree(file=xml)


def parse_channels_by_ids(xml: ElementTree, ns: Dict[str, str]) -> Dict[int, Channel]:
    channels_by_ids = dict()
    for trackElem in xml.findall("xmlns:trackList/xmlns:track", ns):
        channel_id = None
        channel_name = None
        address = None

        for trackSubElem in trackElem:
            tag = trackSubElem.tag.split("}", 1)[1]
            if tag == "title":
                channel_name = trackSubElem.text.strip()
            elif tag == "location":
                address_str = trackSubElem.text.split("@", 1)[1]
                host, port_str = address_str.split(":", 1)
                address = SocketAddress(host, int(port_str))
            elif tag == "extension":
                idElem = trackSubElem.find("{vlc}id", ns)
                if idElem is not None:
                    channel_id = int(idElem.text)

        channels_by_ids[channel_id] = Channel(channel_id, channel_name, address)

    return channels_by_ids


def parse_channel_groups(xml: ElementTree, ns: Dict[str, str],
                         channels_by_ids: Dict[int, Channel]) -> List[ChannelGroup]:
    groups = list()
    for groupElem in xml.findall("xmlns:extension/{vlc}node", ns):
        group_name = groupElem.attrib["title"].strip()
        group_channels = list()

        for groupItemElem in groupElem:
            channel_id = int(groupItemElem.attrib["tid"])
            group_channels.append(channels_by_ids[channel_id])

        groups.append(ChannelGroup(group_name, group_channels))

    return groups


def parse_args():
    parser = ArgumentParser(description="Tool for load Weburg.tv playlist in different formats", add_help=True)
    parser.add_argument("--url", default="http://weburg.tv/playlist.vlc", help="URL of Weburg.tv xml playlist")
    parser.add_argument("--host", required=True, help="Host of proxy")
    parser.add_argument("--port", type=int, required=True, help="Port of proxy")
    parser.add_argument("--multicast-playlist", default="Playlist (multicast).m3u",
                        help="Name for generated multicast playlist")
    parser.add_argument("--unicast-playlist", default="PlayList (unicast).m3u",
                        help="Name for generated unicast playlist")
    parser.add_argument("--sort-by-name", action="store_true", default=False,
                        help="Enable sorting by group and channel names")

    return parser.parse_args()


def main():
    args = parse_args()

    xml = fetch_xml_playlist(args.url)
    ns = {"xmlns": "http://xspf.org/ns/0/",
          "vlc": "http://www.videolan.org/vlc/playlist/ns/0/"}

    channels_by_ids = parse_channels_by_ids(xml, ns)
    groups = parse_channel_groups(xml, ns, channels_by_ids)

    proxy_address = SocketAddress(args.host, args.port)
    write_playlist(args.multicast_playlist, PlaylistType.MULTICAST, groups, proxy_address, args.sort_by_name)
    write_playlist(args.unicast_playlist, PlaylistType.UNICAST, groups, proxy_address, args.sort_by_name)

# Работоспособность проверена под Python 3.5
if __name__ == '__main__':
    main()