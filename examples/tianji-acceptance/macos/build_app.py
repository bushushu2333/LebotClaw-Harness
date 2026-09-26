#!/usr/bin/env python3
"""Package an offline HTML file as a local macOS Cocoa/WebKit app. No game logic."""
import argparse
import hashlib
import json
import platform
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path


def build(html, output, name):
    if platform.system() != 'Darwin':
        raise ValueError('这个构建工具只支持 macOS。')
    html = Path(html).resolve()
    output = Path(output).resolve()
    if not html.is_file() or html.suffix.lower() not in ('.html', '.htm'):
        raise ValueError('请提供真实 HTML 文件。')
    if not name or any(c in name for c in '/\\\x00'):
        raise ValueError('应用名称不能含路径分隔符。')
    if output.exists():
        raise ValueError('输出路径已存在，请指定新的 .app 路径。')
    if output.suffix != '.app':
        raise ValueError('输出路径必须以 .app 结尾。')
    output.parent.mkdir(parents=True, exist_ok=True)
    swift = Path(__file__).with_name('App.swift')
    with tempfile.TemporaryDirectory(prefix='lebot-app-build-', dir=str(output.parent)) as temp:
        bundle = Path(temp) / output.name
        executable = bundle/'Contents'/'MacOS'/'GameHost'
        resources = bundle/'Contents'/'Resources'
        executable.parent.mkdir(parents=True)
        resources.mkdir(parents=True)
        shutil.copyfile(html, resources/'index.html')
        ident = 'local.lebotclaw.game.' + hashlib.sha256(name.encode()).hexdigest()[:12]
        info = {'CFBundleExecutable':'GameHost','CFBundleIdentifier':ident,'CFBundleName':name,
                'CFBundleDisplayName':name,'CFBundleVersion':'1','CFBundleShortVersionString':'1.0',
                'CFBundlePackageType':'APPL','LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True,
                'NSPrincipalClass':'NSApplication'}
        (bundle/'Contents'/'Info.plist').write_bytes(plistlib.dumps(info))
        architecture = 'arm64' if platform.machine()=='arm64' else 'x86_64'
        subprocess.run(['xcrun','swiftc','-O','-target',architecture+'-apple-macosx13.0',
                        '-framework','Cocoa','-framework','WebKit',str(swift),'-o',str(executable)],check=True,timeout=110)
        subprocess.run(['codesign','--force','--sign','-',str(bundle)],check=True,timeout=20)
        subprocess.run(['codesign','--verify','--deep','--strict',str(bundle)],check=True,timeout=20)
        bundle.rename(output)
    digest = hashlib.sha256(html.read_bytes()).hexdigest()
    assert hashlib.sha256((output/'Contents'/'Resources'/'index.html').read_bytes()).hexdigest()==digest
    return {'application':str(output),'html':str(html),'sha256':digest,
            'architecture':architecture,'signing':'local_ad_hoc','requires_harness_server':False}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--html',required=True);p.add_argument('--output',required=True);p.add_argument('--name',default='田忌赛马')
    a=p.parse_args()
    print(json.dumps(build(a.html,a.output,a.name),ensure_ascii=False,indent=2))
