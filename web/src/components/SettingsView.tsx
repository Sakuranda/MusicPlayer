import { useState } from 'react'
import { Check, ExternalLink, Loader2, Smartphone } from 'lucide-react'
import { api, getBase, getToken, setBase, setToken } from '../lib/api'

interface Props {
  onSaved: () => void
}

export default function SettingsView({ onSaved }: Props) {
  const [base, setBaseLocal] = useState(getBase())
  const [token, setTokenLocal] = useState(getToken())
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<'ok' | 'fail' | null>(null)

  const save = () => {
    setBase(base.trim().replace(/\/+$/, ''))
    setToken(token.trim())
    onSaved()
  }

  const test = async () => {
    setTesting(true)
    setTestResult(null)
    setBase(base.trim().replace(/\/+$/, ''))
    setToken(token.trim())
    try {
      await api.health()
      setTestResult('ok')
    } catch {
      setTestResult('fail')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-8 pt-10">
      <h1 className="text-3xl font-semibold tracking-tight mb-8">设置</h1>

      {/* 服务器连接 */}
      <div className="bg-panel border border-line rounded-2xl p-6 mb-6">
        <h2 className="text-base font-medium mb-4">服务器连接</h2>

        <label className="block text-sm text-muted mb-1.5">API 地址</label>
        <input
          value={base}
          onChange={(e) => setBaseLocal(e.target.value)}
          placeholder="留空 = 同源；服务器部署后填 http://45.125.33.88:8080"
          className="w-full bg-bg2 border border-line rounded-xl px-3 py-3 text-sm placeholder:text-faint focus:outline-none focus:border-accent/60 transition-colors"
        />
        <p className="text-[11px] text-faint mt-1.5">
          本地开发留空即可（Vite 会自动代理到 localhost:8080）；正式使用填服务器地址
        </p>

        <label className="block text-sm text-muted mb-1.5 mt-5">API Token（可选）</label>
        <input
          value={token}
          onChange={(e) => setTokenLocal(e.target.value)}
          placeholder="与服务器环境变量 API_TOKEN 保持一致"
          className="w-full bg-bg2 border border-line rounded-xl px-3 py-3 text-sm placeholder:text-faint focus:outline-none focus:border-accent/60 transition-colors"
        />
        <p className="text-[11px] text-faint mt-1.5">
          服务器部署时如果设置了 API_TOKEN，这里填同一个值；留空则不校验
        </p>

        <div className="flex items-center gap-3 mt-5">
          <button
            onClick={test}
            disabled={testing}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-panel2 border border-line text-sm hover:border-accent/50 transition-colors disabled:opacity-50"
          >
            {testing ? <Loader2 size={15} className="spin" /> : <Check size={15} />} 测试连接
          </button>
          {testResult === 'ok' && <span className="text-sm text-emerald-500">✓ 连接成功</span>}
          {testResult === 'fail' && <span className="text-sm text-danger">✗ 连接失败，请检查地址与 Token</span>}
        </div>
      </div>

      {/* iOS 播放 */}
      <div className="bg-panel border border-line rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <Smartphone size={17} className="text-accent" />
          <h2 className="text-base font-medium">iOS 在线播放</h2>
        </div>
        <p className="text-sm text-muted mb-4 leading-relaxed">
          服务器上同时运行 <span className="text-ink">Navidrome</span> 曲库服务（Subsonic 协议），
          iPhone 用免费开源的 <span className="text-ink">Amperfy</span> 即可在线听，支持歌词、离线缓存和 CarPlay。
        </p>
        <ol className="text-sm text-muted space-y-2.5 list-decimal list-inside leading-relaxed">
          <li>App Store 搜索下载 <span className="text-ink">Amperfy</span>（国区可下载，免费）</li>
          <li>
            打开 App → 添加服务器 → 协议选 <span className="text-ink">Subsonic</span>，地址填{' '}
            <code className="bg-bg2 px-1.5 py-0.5 rounded text-accent">http://45.125.33.88:4533</code>
          </li>
          <li>用户名/密码 = Navidrome 账号（首次部署后去 Navidrome 网页注册）</li>
          <li>打开就能看到导入的歌曲，歌词会自动显示（.lrc 文件已随音频生成）</li>
        </ol>
        <a
          href="https://github.com/BLeeEZ/amperfy"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent-soft mt-4 transition-colors"
        >
          了解 Amperfy <ExternalLink size={12} />
        </a>
      </div>

      <button
        onClick={save}
        className="mt-6 px-5 py-3 rounded-xl bg-accent hover:bg-accent-soft text-white text-sm font-medium transition-colors"
      >
        保存设置
      </button>
    </div>
  )
}
