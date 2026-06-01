import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  KeyRound,
  ShieldCheck,
  ShieldAlert,
  Trash2,
  Loader2,
  CheckCircle2,
  XCircle,
  Plug,
  Save,
} from 'lucide-react'

import { testAwsConnection } from '../lib/api'
import {
  useAwsCredentials,
  useSaveAwsCredentials,
  useDeleteAwsCredentials,
} from '../hooks/useAwsCredentials'

// Common regions — a plain text field would also work, but a short list keeps
// typos out and covers the regions an FYP demo is realistically run in.
const REGIONS = [
  'us-east-1',
  'us-east-2',
  'us-west-1',
  'us-west-2',
  'eu-west-1',
  'eu-central-1',
  'ap-south-1',
  'ap-southeast-1',
  'ap-southeast-2',
]

const inputClass =
  'w-full rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 ' +
  'text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent'

const labelClass = 'block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1'

function SettingsPage() {
  const { data: saved, isLoading } = useAwsCredentials()
  const save = useSaveAwsCredentials()
  const remove = useDeleteAwsCredentials()

  const [accessKeyId, setAccessKeyId] = useState('')
  const [secretAccessKey, setSecretAccessKey] = useState('')
  const [region, setRegion] = useState('us-east-1')

  // Test connection lives in its own mutation so we can show its result inline
  // (green/red banner) without it touching the saved-credential cache.
  const test = useMutation({ mutationFn: testAwsConnection })
  const testResult = test.data

  const credsFilled = accessKeyId.trim() && secretAccessKey.trim()
  const payload = { accessKeyId: accessKeyId.trim(), secretAccessKey: secretAccessKey.trim(), region }

  const resetForm = () => {
    setAccessKeyId('')
    setSecretAccessKey('')
    test.reset()
  }

  const handleTest = () => {
    if (!credsFilled) return
    test.mutate(payload)
  }

  const handleSave = (e) => {
    e.preventDefault()
    if (!credsFilled) return
    save.mutate(payload, { onSuccess: resetForm })
  }

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div>
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200">Settings</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          Connect your AWS account so CloudGuard can read your costs and resources
        </p>
      </div>

      {/* Read-only / security note — load-bearing, not decoration. */}
      <div className="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/40 p-4 flex gap-3">
        <ShieldAlert size={20} strokeWidth={1.75} className="shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
        <div className="text-xs text-amber-800 dark:text-amber-200 space-y-1">
          <p className="font-medium">Use READ-ONLY credentials.</p>
          <p>
            CloudGuard only ever reads your billing and resource data. Create an IAM user
            with the AWS-managed <span className="font-mono">ReadOnlyAccess</span> policy — never
            an admin key.
          </p>
          <p className="text-amber-700/80 dark:text-amber-300/80">
            Your secret is encrypted at rest. This is an FYP-grade approach (Fernet + a key in an
            env var); a production system would use a managed KMS and short-lived credentials via
            IAM role assumption.
          </p>
        </div>
      </div>

      {/* Saved credential — masked. Only shown when one exists. */}
      {!isLoading && saved && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 flex items-center gap-4">
          <div className="shrink-0 p-2.5 rounded-lg bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400">
            <ShieldCheck size={20} strokeWidth={1.75} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">AWS account connected</p>
            <p className="text-xs font-mono text-gray-400 dark:text-gray-500 mt-0.5">
              Access key ····{saved.access_key_last4}
              <span className="mx-1.5 text-gray-300 dark:text-gray-600">·</span>
              {saved.region}
            </p>
          </div>
          <button
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-danger border border-red-200 dark:border-red-800 rounded-md hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {remove.isPending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} strokeWidth={2} />}
            Remove
          </button>
        </div>
      )}

      {/* Credential form */}
      <form
        onSubmit={handleSave}
        className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 space-y-4"
      >
        <div className="flex items-center gap-2 text-gray-700 dark:text-gray-200">
          <KeyRound size={18} strokeWidth={1.75} />
          <h3 className="text-sm font-semibold">
            {saved ? 'Update AWS credentials' : 'Add AWS credentials'}
          </h3>
        </div>

        <div>
          <label htmlFor="accessKeyId" className={labelClass}>Access key ID</label>
          <input
            id="accessKeyId"
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={accessKeyId}
            onChange={(e) => { setAccessKeyId(e.target.value); test.reset() }}
            placeholder="AKIA…"
            className={`${inputClass} font-mono`}
          />
        </div>

        <div>
          <label htmlFor="secretAccessKey" className={labelClass}>Secret access key</label>
          <input
            id="secretAccessKey"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={secretAccessKey}
            onChange={(e) => { setSecretAccessKey(e.target.value); test.reset() }}
            placeholder="••••••••••••••••••••••••"
            className={`${inputClass} font-mono`}
          />
        </div>

        <div>
          <label htmlFor="region" className={labelClass}>Region</label>
          <select
            id="region"
            value={region}
            onChange={(e) => { setRegion(e.target.value); test.reset() }}
            className={inputClass}
          >
            {REGIONS.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>

        {/* Inline test-connection result */}
        {testResult && (
          <div
            className={[
              'flex items-start gap-2 rounded-md p-3 text-sm',
              testResult.ok
                ? 'bg-green-50 dark:bg-green-950/40 text-green-700 dark:text-green-300'
                : 'bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300',
            ].join(' ')}
          >
            {testResult.ok
              ? <CheckCircle2 size={16} className="shrink-0 mt-0.5" />
              : <XCircle size={16} className="shrink-0 mt-0.5" />}
            <span>{testResult.detail}</span>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={handleTest}
            disabled={!credsFilled || test.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {test.isPending ? <Loader2 size={14} className="animate-spin" /> : <Plug size={14} strokeWidth={2} />}
            {test.isPending ? 'Testing…' : 'Test connection'}
          </button>
          <button
            type="submit"
            disabled={!credsFilled || save.isPending}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {save.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} strokeWidth={2} />}
            {save.isPending ? 'Saving…' : saved ? 'Update credentials' : 'Save credentials'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default SettingsPage
