"""Rebuild current data warnings separately from historical coverage limitations."""


def refresh_quality(snapshot, expected):
    series = snapshot.get('series', {})
    # These warnings are derived from data, so cached warning lists are never authoritative.
    def managed(issue):
        return (issue.get('derived') or issue.get('item') in series
                or issue.get('item', '').endswith(' 52周回撤')
                or (issue.get('source') == 'PE' and issue.get('item') in ('forward', 'ttm'))
                or issue.get('item') == 'Forward PE直接采集')

    issues = [{**i, 'kind': i.get('kind', 'update')} for i in snapshot.get('issues', []) if not managed(i)]

    def add(source, item, message, kind='update'):
        issues.append({'source': source, 'item': item, 'message': message, 'kind': kind, 'derived': True})

    for key, item in series.items():
        source = item.get('source', '')
        if item.get('status') != 'fresh' or item.get('date') != expected:
            add(source, key, item.get('error') or (
                f"最新观察日 {item['date']}，预期 {expected}" if item.get('date') else '没有有效数据'))
        verification = item.get('verification_status')
        if verification == 'pending_official':
            add(source, key, '最新分发器值待官方新日核对', 'verification')
        elif verification == 'conflict':
            add(source, key, '同口径信源存在未解释冲突，衍生计算停用', 'verification')

    for key, item in snapshot.get('valuation', {}).items():
        reason = item.get('reason')
        if reason:
            kind = 'history' if item.get('status') == 'available' and '样本不足' in reason else 'update'
            add(item.get('source', 'PE'), key, reason, kind)

    publisher = snapshot.get('valuation_publisher', {}).get('forward', {})
    if publisher and not publisher.get('score_ready'):
        add(publisher.get('source', 'Dollar Liquidity'), 'Forward PE直接采集',
            publisher.get('reason') or '源站当前5年分位未取得')

    for key, item in snapshot.get('technicals', {}).items():
        if item.get('drawdown_reason'):
            source_item = series.get(key, {})
            add(source_item.get('high_history_provider', source_item.get('source', '')), key + ' 52周回撤',
                item['drawdown_reason'] + '；不以最高收盘价代替盘中高点', 'history')

    snapshot['issues'] = issues
    snapshot['update_issues'] = [i for i in issues if i['kind'] != 'history']
    snapshot['history_limitations'] = [i for i in issues if i['kind'] == 'history']
    snapshot['quality_counts'] = {'updates': len(snapshot['update_issues']),
                                'history': len(snapshot['history_limitations'])}
    return snapshot
