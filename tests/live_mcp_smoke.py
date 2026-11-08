"""Disposable real FreeCAD -> RPC -> stdio MCP smoke; set FREECAD_EXE."""
import asyncio, json, os, pathlib, secrets, socket, subprocess, sys, tempfile, time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

repo=pathlib.Path(__file__).resolve().parents[1]

async def check(env, folder):
    async with stdio_client(StdioServerParameters(command=sys.executable,
            args=['-m','freecad_mcp.server'],env=env)) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            names={t.name for t in (await session.list_tools()).tools}
            assert {'create_helical_ridge','boolean_solids','transformed_copy',
                    'save_document_copy','open_document','export_objects'} <= names
            assert 'execute_script' not in names
            async def call(name, args):
                result=await session.call_tool(name,args)
                if result.isError: raise RuntimeError(f'{name}: {result.content}')
                return json.loads(result.content[0].text)
            await call('create_document',{'name':'RealMcpSmoke'})
            box=(await call('create_primitive',{'kind':'box','length':20,'width':20,'height':20}))['name']
            cyl=(await call('create_primitive',{'kind':'cylinder','radius':4,'height':25}))['name']
            moved=(await call('transformed_copy',{'name':cyl,'translation':[10,10,0],'axis':[0,0,1]}))['name']
            cut=await call('boolean_solids',{'operation':'cut','first':box,'second':moved})
            assert 0<cut['shape']['volume']<8000
            ridge=await call('create_helical_ridge',{'root_radius':5,'outer_radius':6,'pitch':2.2,
                  'height':8.8,'root_width':1.8,'crest_width':0.4})
            assert ridge['shape']['is_valid']
            fc=str(folder/'part.FCStd'); stl=str(folder/'part.stl'); step=str(folder/'part.step')
            await call('save_document_copy',{'path':fc})
            await call('export_objects',{'path':stl,'names':[cut['name']]})
            await call('export_objects',{'path':step,'names':[cut['name'],ridge['name']]})
            exists=await session.call_tool('export_objects',{'path':stl,'names':[cut['name']]})
            assert exists.isError and pathlib.Path(stl).stat().st_size>0
            opened=await call('open_document',{'path':fc})
            graph=await call('get_document_graph',{'doc_name':opened['name']})
            assert any(o['name']==cut['name'] for o in graph['objects'])

def main():
    with tempfile.TemporaryDirectory() as tmp:
        folder=pathlib.Path(tmp)
        token=folder/'token'; token.write_text(secrets.token_urlsafe(48),encoding='utf-8'); token.chmod(0o600)
        with socket.socket() as s:
            s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
        status=folder/'status'
        env=dict(os.environ,FREECAD_MCP_TEST_REPO=str(repo),FREECAD_MCP_TEST_STATUS=str(status),
                 FREECAD_MCP_TOKEN_FILE=str(token),FREECAD_MCP_PORT=str(port),
                 PYTHONPATH=str(repo/'src'))
        env.pop('FREECAD_MCP_ALLOW_SCRIPT',None)
        kwargs={}
        if sys.platform=='win32':
            info=subprocess.STARTUPINFO(); info.dwFlags|=subprocess.STARTF_USESHOWWINDOW
            info.wShowWindow=subprocess.SW_HIDE; kwargs['startupinfo']=info
        process=subprocess.Popen([os.environ['FREECAD_EXE'],str(repo/'tests'/'freecad_rpc_smoke.FCMacro')],
                                 env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**kwargs)
        try:
            deadline=time.monotonic()+40
            while not status.exists() and time.monotonic()<deadline and process.poll() is None:
                time.sleep(.2)
            if not status.exists(): raise RuntimeError('FreeCAD test RPC did not start')
            text=status.read_text()
            if text!='READY': raise RuntimeError(text)
            asyncio.run(asyncio.wait_for(check(env,folder),timeout=90))
            print('Real FreeCAD + authenticated RPC + stdio MCP modeling smoke passed')
        finally:
            process.terminate()
            process.wait(timeout=10)

if __name__=='__main__': main()
