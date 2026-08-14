import { useEffect, useState } from 'react'
import { api, type EstoqueItem, type EstoqueMaterial, type EstoqueStatus } from '../lib/api'
import { CountUp } from '../components/CountUp'

const rs = (n: number) => `R$ ${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
const qt = (n: number, u: string) => `${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} ${u}`
const dataFmt = (d?: string | null) => (d && d.length >= 10 ? d.split('-').reverse().join('/') : '—')

const STATUS_ROT: Record<EstoqueStatus, string> = {
  ruptura: 'Ruptura', critico: 'Crítico', baixo: 'Baixo', ok: 'Saudável', parado: 'Parado',
}

function Kpi({ label, valor, prefixo, sub, tom }: {
  label: string; valor: number; prefixo?: string; sub?: string; tom?: 'alerta'
}) {
  return (
    <div className="kpi">
      <div className="lbl"><span className={tom ? 'tag red' : 'tag'} />{label}</div>
      <div className="val num" style={tom ? { color: 'var(--accent-ink)' } : undefined}>
        {prefixo}<CountUp value={valor} />
      </div>
      {sub && <div className="foot"><span className="delta">{sub}</span></div>}
    </div>
  )
}

/** Cobertura em dias com cor por severidade. */
function Cobertura({ i }: { i: EstoqueItem }) {
  if (i.status === 'ruptura') return <span className="es-cob es-rup">zerado</span>
  if (i.cobertura_dias == null) return <span className="mut">—</span>
  const cls = i.cobertura_dias < 7 ? 'es-rup' : i.cobertura_dias < 15 ? 'es-crit' : ''
  return <span className={`es-cob ${cls}`}>{i.cobertura_dias} dias</span>
}

export function Estoque({ obra }: { obra: string }) {
  const [data, setData] = useState<EstoqueMaterial | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    setData(null); setErro(null)
    api.estoqueMaterial(obra).then(setData).catch((e: Error) => setErro(e.message))
  }, [obra])

  if (erro) return <div className="errbox"><b>Não foi possível carregar o estoque</b>{erro}</div>
  if (!data) return <div className="skel" style={{ height: 460 }} />
  if (!data.disponivel) {
    return (
      <div className="panel">
        <div className="phead"><div><h2>Estoque — material</h2>
          <div className="ph-sub">{data.mensagem}</div></div></div>
        <div className="empty">As movimentações de almoxarifado desta obra ainda estão sendo coletadas do Sienge.</div>
      </div>
    )
  }

  const alertas = data.alertas ?? []
  const parados = data.parados ?? []
  const st = data.resumo_status ?? { ruptura: 0, critico: 0, baixo: 0, ok: 0, parado: 0 }
  const emRisco = st.ruptura + st.critico + st.baixo

  return (
    <div style={{ display: 'grid', gap: 13 }}>
      <div className="kpis" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>
        <Kpi label="INSUMOS EM ESTOQUE" valor={data.n_insumos ?? 0} sub={`${st.ok} saudáveis`} />
        <Kpi label="VALOR EM ESTOQUE" valor={data.valor_em_estoque ?? 0} prefixo="R$ " sub="capital em material" />
        <Kpi label="CAPITAL PARADO" valor={data.valor_parado ?? 0} prefixo="R$ " sub={`${st.parado} insumos sem consumo`} tom={(data.valor_parado ?? 0) > 0 ? 'alerta' : undefined} />
        <Kpi label="EM RISCO" valor={emRisco} sub={`${st.ruptura} ruptura · ${st.critico} crítico`} tom={emRisco ? 'alerta' : undefined} />
      </div>

      <div className="panel">
        <div className="phead"><div><h2>Risco de ruptura</h2>
          <div className="ph-sub">Insumos com saldo baixo ou zerado <b>e consumo ativo</b>, ordenados por impacto
            (R$ de material consumido por dia). Cobertura = saldo ÷ consumo diário recente.</div></div></div>
        {alertas.length === 0 ? (
          <div className="empty">Nenhum insumo em risco de ruptura na janela atual.</div>
        ) : (
          <div className="tablewrap"><table className="data">
            <thead><tr>
              <th>Insumo</th><th className="rgt">Prior.</th><th className="rgt">Saldo</th>
              <th className="rgt">Consumo/dia</th><th className="rgt">Cobertura</th>
              <th className="rgt">Ruptura</th><th className="rgt">Impacto/dia</th>
            </tr></thead>
            <tbody>
              {alertas.map((i) => (
                <tr key={i.resource_id}>
                  <td className="ct-desc-td"><span className="ct-desc">{i.descricao}</span></td>
                  <td className="rgt"><span className={`es-prio es-${i.status}`}>{i.prioridade}</span></td>
                  <td className="rgt num">{qt(i.saldo, i.unidade)}</td>
                  <td className="rgt num mut">{qt(i.consumo_dia, i.unidade)}</td>
                  <td className="rgt"><Cobertura i={i} /></td>
                  <td className="rgt num mut">{dataFmt(i.data_ruptura)}</td>
                  <td className="rgt"><b className="num">{rs(i.impacto_dia)}</b></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>

      <div className="panel">
        <div className="phead"><div><h2>Capital parado — estoque sem giro</h2>
          <div className="ph-sub">Saldo relevante sem consumo recente. Dinheiro empatado em material que pode ser
            redistribuído, devolvido ou renegociado.</div></div></div>
        {parados.length === 0 ? (
          <div className="empty">Nenhum estoque parado relevante.</div>
        ) : (
          <div className="tablewrap"><table className="data">
            <thead><tr>
              <th>Insumo</th><th className="rgt">Saldo</th>
              <th className="rgt">Sem consumo</th><th className="rgt">Capital parado</th>
            </tr></thead>
            <tbody>
              {parados.map((i) => (
                <tr key={i.resource_id}>
                  <td className="ct-desc-td"><span className="ct-desc">{i.descricao}</span></td>
                  <td className="rgt num mut">{qt(i.saldo, i.unidade)}</td>
                  <td className="rgt num mut">{i.dias_sem_consumo != null ? `${i.dias_sem_consumo} dias` : 'nunca'}</td>
                  <td className="rgt"><b className="num">{rs(i.valor_saldo)}</b></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>

      {(data.unidades_inconsistentes ?? 0) > 0 && (
        <div className="ph-sub" style={{ paddingLeft: 4 }}>
          ⚠ {data.unidades_inconsistentes} insumo(s) com unidade base inconsistente — qualidade de dado a revisar.
        </div>
      )}
      <div className="ph-sub" style={{ paddingLeft: 4, opacity: .7 }}>
        Fonte: movimentações de almoxarifado do Sienge · saldo = entradas − saídas · {STATUS_ROT.ok} = giro normal.
        {data.coletado_em && ` Coletado em ${dataFmt(data.coletado_em.slice(0, 10))}.`}
      </div>
    </div>
  )
}
