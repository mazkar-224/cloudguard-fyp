import SummaryCards from '../components/dashboard/SummaryCards'
import DailyCostsChart from '../components/dashboard/DailyCostsChart'
import ServiceBreakdown from '../components/dashboard/ServiceBreakdown'

function DashboardPage() {
  return (
    <div className="p-6 space-y-6">

      {/* Section label */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200">Cost overview</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Live data from AWS Cost Explorer</p>
      </div>

      {/* Four summary cards */}
      <SummaryCards />

      {/*
        Chart row: line chart on the left (wider) + donut on the right (narrower).
        On small screens they stack vertically; on large screens they sit side by side.
        lg:grid-cols-3 splits into thirds — line chart gets 2, donut gets 1.
      */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <DailyCostsChart />
        </div>
        <div className="lg:col-span-1">
          <ServiceBreakdown />
        </div>
      </div>

    </div>
  )
}

export default DashboardPage
